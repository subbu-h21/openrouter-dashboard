"""Background sync: copies per-generation analytics, keys and credits into SQLite.

The analytics API allows at most 2 dimensions per query, 10,000 rows per query and
31-day ranges for generation-level data. So each time window is fetched as one
"core" query (generation_id + model, with all metrics) plus one query per extra
attribute (generation_id + attribute), joined locally on generation_id. Windows
that come back truncated are split in half and retried.
"""
import calendar
import datetime as dt
import logging
import re
import threading
import time

from . import db, fx
from .config import SYNC_INTERVAL_SECONDS
from .openrouter import MAX_QUERY_ROWS, OpenRouterClient

log = logging.getLogger(__name__)

HOUR = 3600
DAY = 86400
MAX_SPAN = 30 * DAY          # API limit for generation-level ranges is 31 days
MIN_SPAN = HOUR             # windows are whole hours, matching the API's hour buckets
RECENT_OVERLAP = 2 * HOUR     # re-read this much before the last sync point
DEEP_REFRESH_SPAN = 2 * DAY   # periodically re-read this much, to pick up late updates
DEEP_REFRESH_EVERY = HOUR
CREDIT_SNAPSHOT_EVERY = HOUR

# analytics metric -> generations column
CORE_METRICS = {
    "request_count": "requests",
    "total_usage": "cost",
    "byok_usage": "byok_cost",
    "usage_upstream": "cost_upstream",
    "usage_cache": "cost_cache",
    "usage_web": "cost_web",
    "usage_file": "cost_file",
    "usage_data": "cost_data",
    "tokens_total": "tokens_total",
    "tokens_prompt": "tokens_prompt",
    "tokens_completion": "tokens_completion",
    "reasoning_tokens": "tokens_reasoning",
    "cached_tokens": "tokens_cached",
    "avg_latency": "latency_ms",
    "avg_total_time_to_first_token": "ttft_ms",
    "avg_generation_time": "gen_time_ms",
    "avg_throughput": "throughput",
}
INT_COLUMNS = {"requests", "tokens_total", "tokens_prompt", "tokens_completion", "tokens_reasoning", "tokens_cached"}

# analytics dimension -> generations column (each costs one query per window)
ATTRIBUTES = {
    "api_key_id": "api_key",
    "provider": "provider",
    "app": "app",
    "user": "user",
    "finish_reason": "finish_reason",
    "origin": "origin",
    "streamed": "streamed",
}

_ID_EPOCH = re.compile(r"-(\d{10})-")


class _Truncated(Exception):
    pass


def _iso(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_bucket(value: str) -> int:
    return calendar.timegm(time.strptime(value.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S"))


def _num(value, as_int: bool):
    if value is None or value == "":
        return None
    try:
        return int(float(value)) if as_int else float(value)
    except (TypeError, ValueError):
        return None


def _row_ts(row: dict) -> int:
    """Generation ids embed their creation time; use it when it agrees with the hour bucket."""
    bucket_key = next((k for k in row if k.startswith("created_at__")), None)
    bucket = _parse_bucket(row[bucket_key]) if bucket_key and row[bucket_key] else None
    match = _ID_EPOCH.search(row["generation_id"])
    if match:
        epoch = int(match.group(1))
        if bucket is None or bucket <= epoch < bucket + HOUR:
            return epoch
    return bucket if bucket is not None else int(time.time())


def _upsert(conn, rows: list[dict]) -> None:
    if not rows:
        return
    cols = [c for c in rows[0] if c not in ("id", "ts")]
    sql = (
        f"INSERT INTO generations (id, ts, {', '.join(cols)}, updated_at) "
        f"VALUES (?, ?, {', '.join('?' for _ in cols)}, ?) "
        f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in cols)}, "
        f"updated_at = excluded.updated_at"
    )
    now = int(time.time())
    conn.executemany(sql, [(r["id"], r["ts"], *(r[c] for c in cols), now) for r in rows])


class Syncer:
    def __init__(self, client: OpenRouterClient):
        self.client = client
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status = {"phase": "starting", "last_success_at": None, "last_error": None,
                        "last_error_at": None, "backfill_cursor": None}

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="openrouter-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def trigger(self) -> None:
        self._wake.set()

    def status(self) -> dict:
        with self._lock:
            status = dict(self._status)
        with db.session() as conn:
            status["history_start"] = _num(db.get_state(conn, "history_start"), True)
            status["backfill_done"] = db.get_state(conn, "backfill_done") == "1"
            status["synced_to"] = _num(db.get_state(conn, "synced_to"), True)
            status["generations"] = conn.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
        return status

    def _set(self, **kwargs) -> None:
        with self._lock:
            self._status.update(kwargs)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
                self._set(last_success_at=int(time.time()), last_error=None)
            except Exception as e:
                log.exception("sync failed")
                self._set(last_error=str(e), last_error_at=int(time.time()))
            finally:
                self._set(phase="idle")
            self._wake.wait(SYNC_INTERVAL_SECONDS)
            self._wake.clear()

    # ---- one sync pass ---------------------------------------------------
    def run_once(self) -> None:
        fx.refresh_if_stale()  # best effort; a failure keeps the last known rate
        errors = []
        for step in (self._sync_keys, self._sync_credits, self._sync_generations):
            try:
                step()
            except Exception as e:
                log.exception("%s failed", step.__name__)
                errors.append(f"{step.__name__.strip('_')}: {e}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def _sync_keys(self) -> None:
        self._set(phase="syncing keys")
        keys = self.client.list_keys()
        now = int(time.time())
        with db.session() as conn:
            conn.execute("UPDATE api_keys SET present = 0")
            conn.executemany(
                """INSERT INTO api_keys (hash, name, label, disabled, limit_usd, limit_remaining, limit_reset,
                       include_byok_in_limit, usage, usage_daily, usage_weekly, usage_monthly, byok_usage,
                       created_at, updated_at, expires_at, last_used_at, workspace_id, present, seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(hash) DO UPDATE SET
                       name = excluded.name, label = excluded.label, disabled = excluded.disabled,
                       limit_usd = excluded.limit_usd, limit_remaining = excluded.limit_remaining,
                       limit_reset = excluded.limit_reset, include_byok_in_limit = excluded.include_byok_in_limit,
                       usage = excluded.usage, usage_daily = excluded.usage_daily,
                       usage_weekly = excluded.usage_weekly, usage_monthly = excluded.usage_monthly,
                       byok_usage = excluded.byok_usage, created_at = excluded.created_at,
                       updated_at = excluded.updated_at, expires_at = excluded.expires_at,
                       last_used_at = excluded.last_used_at, workspace_id = excluded.workspace_id,
                       present = 1, seen_at = excluded.seen_at""",
                [(k["hash"], k.get("name"), k.get("label"), int(bool(k.get("disabled"))), k.get("limit"),
                  k.get("limit_remaining"), k.get("limit_reset"), int(bool(k.get("include_byok_in_limit"))),
                  k.get("usage"), k.get("usage_daily"), k.get("usage_weekly"), k.get("usage_monthly"),
                  k.get("byok_usage"), k.get("created_at"), k.get("updated_at"), k.get("expires_at"),
                  k.get("last_used_at"), k.get("workspace_id"), now) for k in keys],
            )

    def _sync_credits(self) -> None:
        self._set(phase="syncing credits")
        credits = self.client.credits()
        now = int(time.time())
        with db.session() as conn:
            last = conn.execute("SELECT * FROM credit_snapshots ORDER BY ts DESC LIMIT 1").fetchone()
            changed = not last or (last["total_credits"], last["total_usage"]) != (
                credits["total_credits"], credits["total_usage"])
            if changed or now - last["ts"] >= CREDIT_SNAPSHOT_EVERY:
                conn.execute("INSERT OR REPLACE INTO credit_snapshots (ts, total_credits, total_usage) VALUES (?, ?, ?)",
                             (now, credits["total_credits"], credits["total_usage"]))

    def _sync_generations(self) -> None:
        now = int(time.time())
        with db.session() as conn:
            done = db.get_state(conn, "backfill_done") == "1"
            cursor = _num(db.get_state(conn, "backfill_cursor"), True)
            synced_to = _num(db.get_state(conn, "synced_to"), True)
            last_deep = _num(db.get_state(conn, "last_deep_refresh"), True) or 0

        if not done:
            if cursor is None:
                self._set(phase="finding history start")
                history_start = self._find_history_start() or now
                cursor = history_start
                with db.session() as conn:
                    db.set_state(conn, "history_start", history_start)
                    db.set_state(conn, "backfill_cursor", cursor)
            self._set(phase="backfilling history", backfill_cursor=cursor)

            def save_cursor(t: int) -> None:
                with db.session() as conn:
                    db.set_state(conn, "backfill_cursor", t)
                self._set(backfill_cursor=t)

            self._sync_range(cursor, now, save_cursor)
            with db.session() as conn:
                db.set_state(conn, "backfill_done", 1)
                db.set_state(conn, "synced_to", now)
                db.set_state(conn, "last_deep_refresh", now)
            return

        self._set(phase="syncing recent")
        start = (synced_to or now) - RECENT_OVERLAP
        deep = now - last_deep >= DEEP_REFRESH_EVERY
        if deep:
            start = min(start, now - DEEP_REFRESH_SPAN)
        self._sync_range(start, now, lambda t: None)
        with db.session() as conn:
            db.set_state(conn, "synced_to", now)
            if deep:
                db.set_state(conn, "last_deep_refresh", now)

    def _find_history_start(self) -> int | None:
        """Earliest day with any requests, searching back one year at a time."""
        end, earliest = int(time.time()) + DAY, None
        for _ in range(5):
            start = end - 365 * DAY
            rows, _ = self.client.analytics_query({
                "metrics": ["request_count"], "granularity": "day", "limit": 400,
                "time_range": {"start": _iso(start), "end": _iso(end)},
            })
            days = sorted(r["date__day"] for r in rows if (_num(r.get("request_count"), True) or 0) > 0)
            if not days:
                break
            earliest = calendar.timegm(time.strptime(days[0][:10], "%Y-%m-%d"))
            if earliest > start + 2 * DAY:
                break
            end = start
        return earliest - DAY if earliest is not None else None

    def _sync_range(self, start: int, end: int, on_progress) -> None:
        start = start // HOUR * HOUR
        end = -(-end // HOUR) * HOUR
        span, t = 7 * DAY, start
        while t < end and not self._stop.is_set():
            window_end = min(t + span, end)
            try:
                rows = self._sync_window(t, window_end)
            except _Truncated:
                if span <= MIN_SPAN:
                    raise RuntimeError(f"more than {MAX_QUERY_ROWS} generations in one hour at {_iso(t)}")
                span = max(span // 2 // HOUR * HOUR, MIN_SPAN)
                continue
            t = window_end
            on_progress(t)
            if rows < MAX_QUERY_ROWS * 0.3:
                span = min(span * 2, MAX_SPAN)

    def _query(self, start: int, end: int, dimension: str, metrics: list[str]) -> list[dict]:
        rows, truncated = self.client.analytics_query({
            "metrics": metrics,
            "dimensions": ["generation_id", dimension],
            "granularity": "hour",
            "time_range": {"start": _iso(start), "end": _iso(end)},
            "limit": MAX_QUERY_ROWS,
        })
        if truncated:
            raise _Truncated()
        return [r for r in rows if r.get("generation_id")]

    def _sync_window(self, start: int, end: int) -> int:
        core = self._query(start, end, "model", list(CORE_METRICS))
        batches = [[
            {"id": r["generation_id"], "ts": _row_ts(r), "model": r.get("model"),
             **{col: _num(r.get(metric), col in INT_COLUMNS) for metric, col in CORE_METRICS.items()}}
            for r in core
        ]]
        for dimension, col in ATTRIBUTES.items():
            batch = []
            for r in self._query(start, end, dimension, ["request_count"]):
                value = r.get(dimension)
                row = {"id": r["generation_id"], "ts": _row_ts(r)}
                if dimension == "streamed":
                    row[col] = None if value is None else int(str(value).lower() == "true")
                else:
                    row[col] = value
                if dimension == "user":
                    row["user_email"] = r.get("user_email")
                batch.append(row)
            batches.append(batch)
        with db.session() as conn:
            for batch in batches:
                _upsert(conn, batch)
        log.info("synced %s .. %s: %d generations", _iso(start), _iso(end), len(core))
        return len(core)
