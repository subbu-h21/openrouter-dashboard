"""USD -> INR exchange rate: fetched from Frankfurter (ECB reference rates) and cached in SQLite."""
import json
import logging
import time
import urllib.request

from . import db

log = logging.getLogger(__name__)

REFRESH_EVERY = 12 * 3600
SOURCES = (
    "https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR",
    "https://api.frankfurter.app/latest?from=USD&to=INR",
)


def current() -> dict:
    with db.session() as conn:
        rate = db.get_state(conn, "fx_usd_inr")
        return {
            "usd_inr": float(rate) if rate else None,
            "date": db.get_state(conn, "fx_date"),
            "fetched_at": int(db.get_state(conn, "fx_fetched_at") or 0) or None,
        }


def refresh_if_stale() -> None:
    """Never raises: on failure the last stored rate stays in use."""
    if time.time() - (current()["fetched_at"] or 0) < REFRESH_EVERY:
        return
    for url in SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "openrouter-usage-dashboard"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            rate = float(data["rates"]["INR"])
            if not 10 < rate < 1000:
                raise ValueError(f"implausible rate {rate}")
        except Exception as e:
            log.warning("exchange rate fetch from %s failed: %s", url, e)
            continue
        with db.session() as conn:
            db.set_state(conn, "fx_usd_inr", rate)
            db.set_state(conn, "fx_date", data.get("date"))
            db.set_state(conn, "fx_fetched_at", int(time.time()))
        log.info("USD->INR rate %.4f (%s)", rate, data.get("date"))
        return
