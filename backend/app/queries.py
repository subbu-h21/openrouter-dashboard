"""Aggregations over the local generations table."""
import calendar
import sqlite3
import time
from datetime import datetime

GROUP_COLUMNS = {
    "model": "model",
    "api_key": "api_key",
    "provider": "provider",
    "app": "app",
    "user": "user",
    "finish_reason": "finish_reason",
    "origin": "origin",
}
FILTER_COLUMNS = ("api_key", "model", "provider", "app", "user", "finish_reason")
NULL_TOKEN = "__null__"   # filter value meaning "attribute is missing"
OTHER_KEY = "__other__"
TOP_SERIES = 8            # categorical palette size; the rest folds into "Other"

TOKENS = "COALESCE(tokens_total, COALESCE(tokens_prompt, 0) + COALESCE(tokens_completion, 0))"

# preset -> (bucket kind, bucket count; None = from first generation)
RANGES = {
    "1h": ("minute", 60),
    "1d": ("hour", 24),
    "7d": ("day", 7),
    "1m": ("day", 30),
    "3m": ("week", 13),
    "1y": ("month", 12),
    "all": ("month", None),
}
UNIT = {"minute": 60, "hour": 3600, "day": 86400, "week": 7 * 86400}


# ---- time ranges ---------------------------------------------------------

def _bucket_sql(kind: str, off: int) -> str:
    if kind == "month":
        return f"strftime('%Y-%m', ts + {off}, 'unixepoch')"
    if kind == "week":  # Monday-aligned; 1970-01-01 was a Thursday
        day = f"((ts + {off}) / 86400)"
        return f"(({day} - (({day} + 3) % 7)) * 86400 - {off})"
    unit = UNIT[kind]
    return f"(((ts + {off}) / {unit}) * {unit} - {off})"


def _month_start(year: int, month: int, off: int) -> int:
    return calendar.timegm((year, month, 1, 0, 0, 0)) - off


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + n
    return index // 12, index % 12 + 1


def resolve_range(conn: sqlite3.Connection, key: str, tz_minutes: int) -> dict:
    if key not in RANGES:
        raise ValueError(f"unknown range {key!r}")
    kind, count = RANGES[key]
    off = int(tz_minutes) * 60
    local_now = int(time.time()) + off

    if kind == "month":
        now_t = time.gmtime(local_now)
        if count is None:
            first = conn.execute("SELECT MIN(ts) FROM generations").fetchone()[0]
            first_t = time.gmtime((first if first is not None else local_now - off) + off)
            count = (now_t.tm_year - first_t.tm_year) * 12 + now_t.tm_mon - first_t.tm_mon + 1
        months = [_add_months(now_t.tm_year, now_t.tm_mon, i - count + 1) for i in range(count + 1)]
        buckets = [_month_start(y, m, off) for y, m in months]
        labels = {f"{y:04d}-{m:02d}": b for (y, m), b in zip(months, buckets)}
        return {"key": key, "kind": kind, "tz_offset": off, "start": buckets[0], "end": buckets[-1],
                "buckets": buckets[:-1], "month_labels": labels}

    unit = UNIT[kind]
    if kind == "week":
        day = local_now // 86400
        last = (day - (day + 3) % 7) * 86400
    else:
        last = local_now // unit * unit
    first = last - (count - 1) * unit
    buckets = [first + i * unit - off for i in range(count)]
    return {"key": key, "kind": kind, "tz_offset": off, "start": buckets[0], "end": buckets[-1] + unit,
            "buckets": buckets}


def _bucket_value(rng: dict, raw):
    if rng["kind"] == "month":
        return rng["month_labels"].get(raw)
    return int(raw)


# ---- filters -------------------------------------------------------------

def _where(rng: dict | None, filters: dict) -> tuple[str, list]:
    clauses, params = [], []
    if rng is not None:
        clauses.append("ts >= ? AND ts < ?")
        params += [rng["start"], rng["end"]]
    for name in FILTER_COLUMNS:
        value = filters.get(name)
        if value is None or value == "":
            continue
        if value == NULL_TOKEN:
            clauses.append(f"{name} IS NULL")
        else:
            clauses.append(f"{name} = ?")
            params.append(value)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


# ---- activity ------------------------------------------------------------

def timeseries(conn: sqlite3.Connection, rng: dict, group_by: str, filters: dict) -> dict:
    col = GROUP_COLUMNS[group_by]
    where, params = _where(rng, filters)
    rows = conn.execute(
        f"""SELECT {_bucket_sql(rng['kind'], rng['tz_offset'])} AS b, {col} AS g,
                   SUM(COALESCE(cost, 0)) AS cost, SUM({TOKENS}) AS tokens, SUM(COALESCE(requests, 1)) AS requests
            FROM generations {where} GROUP BY b, g""",
        params,
    ).fetchall()

    metrics = ("cost", "tokens", "requests")
    totals = {m: {} for m in metrics}
    for r in rows:
        for m in metrics:
            totals[m][r["g"]] = totals[m].get(r["g"], 0) + (r[m] or 0)

    # One series set shared by all three charts, so an entity keeps its colour everywhere:
    # take the leaders of each metric in turn until the palette is full; the rest is "Other".
    ranked = {m: sorted((g for g, v in totals[m].items() if v > 0), key=lambda g: -totals[m][g]) for m in metrics}
    chosen: list = []
    for i in range(max((len(v) for v in ranked.values()), default=0)):
        for m in metrics:
            if i < len(ranked[m]) and ranked[m][i] not in chosen and len(chosen) < TOP_SERIES:
                chosen.append(ranked[m][i])
    ids = {g: f"s{i}" for i, g in enumerate(chosen)}
    other_id = f"s{TOP_SERIES}"

    series = [{"id": ids[g], "key": g, "totals": {m: totals[m].get(g, 0) for m in metrics}} for g in chosen]
    other_totals = {m: sum(v for g, v in totals[m].items() if g not in ids) for m in metrics}
    if any(other_totals.values()):
        series.append({"id": other_id, "key": OTHER_KEY, "totals": other_totals})

    result = {"kind": rng["kind"], "buckets": rng["buckets"], "series": series, "metrics": {}}
    for m in metrics:
        points = {b: {"t": b} for b in rng["buckets"]}
        for r in rows:
            b = _bucket_value(rng, r["b"])
            if b not in points or not r[m]:
                continue
            sid = ids.get(r["g"], other_id)
            points[b][sid] = points[b].get(sid, 0) + r[m]
        result["metrics"][m] = {"total": sum(totals[m].values()), "points": [points[b] for b in rng["buckets"]]}
    return result


_AGGREGATES = f"""
    SUM(COALESCE(cost, 0))              AS cost,
    SUM(COALESCE(byok_cost, 0))         AS byok_cost,
    SUM(COALESCE(requests, 1))          AS requests,
    SUM({TOKENS})                       AS tokens,
    SUM(COALESCE(tokens_prompt, 0))     AS tokens_prompt,
    SUM(COALESCE(tokens_completion, 0)) AS tokens_completion,
    SUM(COALESCE(tokens_reasoning, 0))  AS tokens_reasoning,
    SUM(COALESCE(tokens_cached, 0))     AS tokens_cached,
    AVG(latency_ms)                     AS avg_latency_ms,
    AVG(ttft_ms)                        AS avg_ttft_ms,
    AVG(throughput)                     AS avg_throughput,
    MIN(ts)                             AS first_ts,
    MAX(ts)                             AS last_ts
"""


def breakdown(conn: sqlite3.Connection, rng: dict, group_by: str, filters: dict) -> list[dict]:
    col = GROUP_COLUMNS[group_by]
    where, params = _where(rng, filters)
    rows = conn.execute(
        f"SELECT {col} AS key, {_AGGREGATES} FROM generations {where} GROUP BY {col} ORDER BY cost DESC, requests DESC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def summary(conn: sqlite3.Connection, rng: dict, filters: dict) -> dict:
    where, params = _where(rng, filters)
    current = dict(conn.execute(f"SELECT {_AGGREGATES} FROM generations {where}", params).fetchone())

    previous = None
    if rng["key"] != "all":
        span = rng["end"] - rng["start"]
        prev_rng = {**rng, "start": rng["start"] - span, "end": rng["start"]}
        where, params = _where(prev_rng, filters)
        previous = dict(conn.execute(
            f"SELECT SUM(COALESCE(cost, 0)) AS cost, SUM(COALESCE(requests, 1)) AS requests, SUM({TOKENS}) AS tokens "
            f"FROM generations {where}", params).fetchone())

    return {"current": current, "previous": previous, "credits": credits_summary(conn)}


def credits_summary(conn: sqlite3.Connection) -> dict | None:
    snap = conn.execute("SELECT * FROM credit_snapshots ORDER BY ts DESC LIMIT 1").fetchone()
    if not snap:
        return None
    week_cost = conn.execute("SELECT SUM(COALESCE(cost, 0)) FROM generations WHERE ts >= ?",
                             (int(time.time()) - 7 * 86400,)).fetchone()[0] or 0
    remaining = snap["total_credits"] - snap["total_usage"]
    daily = week_cost / 7
    return {
        "as_of": snap["ts"],
        "total_credits": snap["total_credits"],
        "total_usage": snap["total_usage"],
        "remaining": remaining,
        "avg_daily_spend_7d": daily,
        "days_left": remaining / daily if daily > 0 else None,
    }


def credit_history(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT ts, total_credits, total_usage FROM credit_snapshots ORDER BY ts").fetchall()
    return [{"t": r["ts"], "remaining": r["total_credits"] - r["total_usage"], **dict(r)} for r in rows]


# ---- logs ----------------------------------------------------------------

LOG_SORTS = {"ts": "ts", "cost": "cost", "tokens": TOKENS, "latency": "latency_ms", "throughput": "throughput"}
LOG_COLUMNS = """id, ts, model, api_key, provider, app, user, finish_reason, origin, streamed, cost, byok_cost,
                 tokens_total, tokens_prompt, tokens_completion, tokens_reasoning, tokens_cached,
                 latency_ms, ttft_ms, gen_time_ms, throughput"""


def _log_query(rng: dict | None, filters: dict, search: str | None) -> tuple[str, list]:
    where, params = _where(rng, filters)
    if search:
        where += (" AND " if where else "WHERE ") + "id LIKE ?"
        params.append(f"%{search}%")
    return where, params


def logs(conn: sqlite3.Connection, rng: dict | None, filters: dict, search: str | None,
         sort: str, direction: str, page: int, page_size: int) -> dict:
    where, params = _log_query(rng, filters, search)
    order = f"{LOG_SORTS[sort]} {'ASC' if direction == 'asc' else 'DESC'}, id"
    total = conn.execute(f"SELECT COUNT(*) FROM generations {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {LOG_COLUMNS} FROM generations {where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    return {"total": total, "page": page, "page_size": page_size, "rows": [dict(r) for r in rows]}


def iter_logs(conn: sqlite3.Connection, rng: dict | None, filters: dict, search: str | None):
    where, params = _log_query(rng, filters, search)
    cursor = conn.execute(f"SELECT {LOG_COLUMNS} FROM generations {where} ORDER BY ts DESC", params)
    yield [d[0] for d in cursor.description]
    for row in cursor:
        yield list(row)


# ---- filter options ------------------------------------------------------

def options(conn: sqlite3.Connection) -> dict:
    """All-time values per dimension, ordered by spend (also used for stable series colours)."""
    result = {}
    for name, col in GROUP_COLUMNS.items():
        rows = conn.execute(
            f"SELECT {col} AS value, SUM(COALESCE(cost, 0)) AS cost, COUNT(*) AS requests "
            f"FROM generations GROUP BY {col} ORDER BY cost DESC, requests DESC LIMIT 500"
        ).fetchall()
        result[name] = [dict(r) for r in rows]
    return result


# ---- keys ----------------------------------------------------------------

def keys(conn: sqlite3.Connection) -> list[dict]:
    now = int(time.time())
    stats = {
        r["api_key"]: dict(r)
        for r in conn.execute(
            """SELECT api_key,
                      SUM(COALESCE(cost, 0)) AS cost_all,
                      SUM(CASE WHEN ts >= ? THEN COALESCE(cost, 0) ELSE 0 END) AS cost_24h,
                      SUM(CASE WHEN ts >= ? THEN COALESCE(cost, 0) ELSE 0 END) AS cost_7d,
                      SUM(CASE WHEN ts >= ? THEN COALESCE(cost, 0) ELSE 0 END) AS cost_30d,
                      SUM(COALESCE(requests, 1)) AS requests_all,
                      SUM(CASE WHEN ts >= ? THEN COALESCE(requests, 1) ELSE 0 END) AS requests_30d,
                      MAX(ts) AS last_request_ts
               FROM generations GROUP BY api_key""",
            (now - 86400, now - 7 * 86400, now - 30 * 86400, now - 30 * 86400),
        )
    }
    top_models = {}
    for r in conn.execute(
        """SELECT api_key, model, SUM(COALESCE(cost, 0)) AS cost FROM generations
           WHERE ts >= ? GROUP BY api_key, model ORDER BY cost DESC""", (now - 30 * 86400,)):
        top_models.setdefault(r["api_key"], r["model"])

    key_rows = [dict(r) for r in conn.execute("SELECT * FROM api_keys ORDER BY created_at DESC")]
    name_counts: dict = {}
    for k in key_rows:
        name_counts[k["name"]] = name_counts.get(k["name"], 0) + 1

    result = []
    for k in key_rows:
        flags = []
        if not k["present"]:
            flags.append("deleted")
        if k["disabled"]:
            flags.append("disabled")
        if k["expires_at"] and _iso_to_ts(k["expires_at"]) < now:
            flags.append("expired")
        if k["limit_usd"] is None:
            flags.append("no_limit")
        elif k["limit_usd"] > 0 and (k["limit_remaining"] or 0) / k["limit_usd"] < 0.1:
            flags.append("near_limit")
        if not k["expires_at"]:
            flags.append("no_expiry")
        if not k["last_used_at"] or _iso_to_ts(k["last_used_at"]) < now - 30 * 86400:
            flags.append("unused_30d")
        if name_counts[k["name"]] > 1:
            flags.append("duplicate_name")
        result.append({**k, "stats": stats.get(k["name"]), "top_model_30d": top_models.get(k["name"]),
                       "flags": flags})

    # Keys seen in usage data but no longer listed by OpenRouter (e.g. deleted before the first sync).
    listed = {k["name"] for k in key_rows}
    for name, s in stats.items():
        if name is None or name in listed:
            continue
        result.append({"hash": None, "name": name, "label": None, "present": 0, "stats": s,
                       "top_model_30d": top_models.get(name), "flags": ["deleted"]})
    return result


def _iso_to_ts(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
