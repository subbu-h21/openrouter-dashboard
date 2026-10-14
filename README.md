# OpenRouter Usage Dashboard

A self-hosted, read-only dashboard for an OpenRouter account: spend, tokens and requests over
time, broken down by model, API key, provider, app or creator; a searchable request log with CSV
export; and an API key overview with limits and warnings.

## How it works

- **Backend** (`backend/`, FastAPI): a background thread pulls data from OpenRouter with a
  *management key* and stores it in SQLite (`data/dashboard.db`). The key never leaves the server.
- **Frontend** (`frontend/`, React + Recharts, built with Vite): served by the backend from
  `frontend/dist`.
- **Data**: one row per request (generation), imported from OpenRouter's Analytics API. On first
  start the full history is backfilled; afterwards new requests are pulled every
  `SYNC_INTERVAL_SECONDS` (default 5 minutes), and the last 48 hours are re-read hourly to pick up
  late updates. Key metadata and the credit balance are refreshed on every sync.
- Because the data is stored locally, history is kept even if OpenRouter's retention is shorter.

## Setup (Windows)

Requires Python 3.10+ and Node.js 20+ on PATH.

1. Double-click **`setup.bat`** (or run it from a terminal). It creates the Python environment,
   installs packages, builds the frontend, creates `.env` from `.env.example` if it's missing,
   and asks you to choose a dashboard username and password (only a salted hash is saved).
2. Put an OpenRouter **management key** in `.env`
   (create one at https://openrouter.ai/settings/management-keys, with an expiry date):

   ```
   OPENROUTER_MANAGEMENT_KEY=...
   ```

3. Double-click **`start.bat`**. The dashboard runs at http://127.0.0.1:8787 until you close the
   window or press Ctrl+C. To use another port: `set "PORT=8788" && start.bat`.

Run `setup.bat` again after pulling changes or editing the frontend.

### Development

```powershell
# terminal 1 – API on :8787
cd backend; .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
# terminal 2 – Vite dev server on :5173, proxies /api to :8787
cd frontend; npm run dev
```

After frontend changes, run `npm run build` in `frontend/` and restart the backend.

## Sharing it through a tunnel

The server only listens on `127.0.0.1`. To share it, point a tunnel at `http://127.0.0.1:8787`, for
example Cloudflare Tunnel (`cloudflared tunnel --url http://127.0.0.1:8787`) or ngrok
(`ngrok http 8787`). The tunnel must terminate HTTPS; the login cookie is then marked `Secure`.

Security notes:

- Everything except the login page requires logging in. There is a single login, stored in
  `.env` (the password only as a salted PBKDF2 hash); anyone with it sees all keys and spend.
- To change the login: `cd backend` then `.venv\Scripts\python -m app.set_login`, and restart.
  Changing it logs out every existing session.
- Failed logins are throttled: 5 per client per 15 minutes, and 30 in total per 15 minutes
  (which also locks out the admin for that window; restarting the server clears it).
- `.env` and `data/` are git-ignored and must never be committed: `.env` holds the management key
  and login, `data/` holds the synced usage (key names, emails, spend) and the session secret.
- The dashboard is read-only. It never creates, edits or deletes keys, but the management key
  itself *can*, so keep `.env` private and set an expiry on the key.

## Data notes

- Request-level data comes from OpenRouter's Analytics API (`generation_id` dimension). OpenRouter's
  own monthly totals can include a handful of requests that have no request-level record (a few
  per month, fractions of a cent), so totals here may be very slightly lower.
- Usage data identifies API keys by **name**. Keys that share a name are combined in the
  request-based numbers (flagged "Duplicate name" on the Keys page).
- A key flagged "Not in key list" has usage history but is no longer returned by OpenRouter's
  key list (deleted, or in another workspace).
- Times are shown in the browser's time zone; days/weeks/months are bucketed in that zone.
