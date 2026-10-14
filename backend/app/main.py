"""FastAPI app: JSON API under /api, the built React frontend everywhere else."""
import csv
import io
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, db, fx, queries
from .openrouter import OpenRouterClient
from .sync import Syncer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

config.validate()
db.init()
syncer = Syncer(OpenRouterClient(config.MANAGEMENT_KEY))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    syncer.start()
    yield
    syncer.stop()


# No /docs or /openapi.json: this is exposed through a public tunnel.
app = FastAPI(title="OpenRouter Dashboard", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---- auth ----------------------------------------------------------------

class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    client = auth.client_id(request)
    if not auth.login_allowed(client):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    if not auth.check_credentials(body.username, body.password):
        auth.record_failure(client)
        time.sleep(1)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    response.set_cookie(
        auth.COOKIE_NAME, auth.create_token(), max_age=config.SESSION_DAYS * 86400,
        httponly=True, samesite="strict", secure=request.url.scheme == "https", path="/",
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"authenticated": auth.verify_token(request.cookies.get(auth.COOKIE_NAME))}


# ---- shared query parameters ---------------------------------------------

def filters(api_key: str | None = None, model: str | None = None, provider: str | None = None,
            app: str | None = None, user: str | None = None, finish_reason: str | None = None) -> dict:
    return {"api_key": api_key, "model": model, "provider": provider, "app": app, "user": user,
            "finish_reason": finish_reason}


def time_range(conn, range_key: str, tz: int) -> dict:
    try:
        return queries.resolve_range(conn, range_key, max(-840, min(840, tz)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


def check_group(group_by: str) -> str:
    if group_by not in queries.GROUP_COLUMNS:
        raise HTTPException(status_code=400, detail=f"group_by must be one of {list(queries.GROUP_COLUMNS)}")
    return group_by


api = Depends(auth.require_auth)


# ---- data ----------------------------------------------------------------

@app.get("/api/summary", dependencies=[api])
def get_summary(range: str = "1m", tz: int = 0, f: dict = Depends(filters)):
    with db.session() as conn:
        rng = time_range(conn, range, tz)
        return {"range": rng, **queries.summary(conn, rng, f)}


@app.get("/api/timeseries", dependencies=[api])
def get_timeseries(range: str = "1m", tz: int = 0, group_by: str = "model", f: dict = Depends(filters)):
    group_by = check_group(group_by)
    with db.session() as conn:
        rng = time_range(conn, range, tz)
        return queries.timeseries(conn, rng, group_by, f)


@app.get("/api/breakdown", dependencies=[api])
def get_breakdown(range: str = "1m", tz: int = 0, group_by: str = "model", f: dict = Depends(filters)):
    group_by = check_group(group_by)
    with db.session() as conn:
        rng = time_range(conn, range, tz)
        return {"group_by": group_by, "rows": queries.breakdown(conn, rng, group_by, f)}


@app.get("/api/logs", dependencies=[api])
def get_logs(range: str = "all", tz: int = 0, q: str | None = None, sort: str = "ts", direction: str = "desc",
             page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), f: dict = Depends(filters)):
    if sort not in queries.LOG_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {list(queries.LOG_SORTS)}")
    with db.session() as conn:
        rng = time_range(conn, range, tz)
        return queries.logs(conn, rng, f, q, sort, direction, page, page_size)


@app.get("/api/logs.csv", dependencies=[api])
def get_logs_csv(range: str = "all", tz: int = 0, q: str | None = None, f: dict = Depends(filters)):
    # Starlette may advance a sync generator from different threads, so this connection opts out
    # of sqlite's same-thread check; it is only ever used by one iteration at a time.
    conn = db.connect(check_same_thread=False)
    try:
        rng = time_range(conn, range, tz)
    except HTTPException:
        conn.close()
        raise

    usd_inr = fx.current()["usd_inr"]

    def rows():
        try:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            cost_index = None
            for i, row in enumerate(queries.iter_logs(conn, rng, f, q)):
                if usd_inr:  # extra column: cost converted at the current rate
                    if i == 0:
                        cost_index = row.index("cost")
                        row = [*row, f"cost_inr (at {usd_inr})"]
                    else:
                        cost = row[cost_index]
                        row = [*row, None if cost is None else round(cost * usd_inr, 4)]
                writer.writerow(row)
                if i % 500 == 0:
                    yield buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate()
            yield buffer.getvalue()
        finally:
            conn.close()

    filename = f"openrouter-logs-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(rows(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/options", dependencies=[api])
def get_options():
    with db.session() as conn:
        return queries.options(conn)


@app.get("/api/fx", dependencies=[api])
def get_fx():
    return fx.current()


@app.get("/api/keys", dependencies=[api])
def get_keys():
    with db.session() as conn:
        return {"keys": queries.keys(conn)}


@app.get("/api/credits", dependencies=[api])
def get_credits():
    with db.session() as conn:
        return {"current": queries.credits_summary(conn), "history": queries.credit_history(conn)}


@app.get("/api/sync", dependencies=[api])
def get_sync_status():
    return syncer.status()


@app.post("/api/sync", dependencies=[api])
def trigger_sync():
    syncer.trigger()
    return {"ok": True}


# ---- frontend ------------------------------------------------------------

DIST = config.FRONTEND_DIST.resolve()
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    index = DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Frontend not built. Run `npm run build` in frontend/.")
    candidate = (DIST / path).resolve()
    if path and candidate.is_file() and candidate.is_relative_to(DIST):
        return FileResponse(candidate)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
