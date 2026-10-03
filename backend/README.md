# Backend (FastAPI)

```text
backend/
├── main.py                  app setup: CORS, error handlers, startup
├── config/settings.py       ALL configuration, read from environment variables
├── routes/                  HTTP endpoints (email_routes.py, health_routes.py)
├── services/
│   ├── gmail_service.py     talks to Gmail (OAuth, pagination, parsing)
│   ├── ai_service.py        Gemini classification + briefing + validation + fallback
│   ├── mongodb_service.py   the only file that touches MongoDB
│   └── sync_service.py      Gmail -> AI -> MongoDB, without duplicates
├── models/email.py          validation + response models
├── utils/                   logger (redacts secrets), API-key check, HTML cleaner
├── scripts/                 gmail_auth.py (one-time login), check_*.py (manual checks)
└── tests/                   offline tests (no real Gmail / Mongo / Gemini needed)
```

## Run locally

Windows (PowerShell):

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then edit .env with your own values
python scripts/gmail_auth.py  # ONE time: opens a browser, creates token.json
uvicorn main:app --reload
```

macOS / Linux:

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env
python scripts/gmail_auth.py
uvicorn main:app --reload
```

Check it: <http://localhost:8000/healthz>, <http://localhost:8000/status>, <http://localhost:8000/docs>.

Frontend: create `frontend/.env` containing `VITE_API_URL=http://localhost:8000`, then `npm install && npm run dev`.

> **Do not regenerate `requirements.txt` with `pip freeze > requirements.txt` in PowerShell** –
> PowerShell writes UTF-16, which breaks `pip` on Render. Edit the file by hand, or use
> `pip freeze | Out-File -Encoding utf8 requirements.txt`.

## Tests and manual checks

```bash
pip install -r requirements-dev.txt
pytest                         # offline, takes a few seconds
python scripts/check_mongodb.py
python scripts/check_ai.py
python scripts/check_gmail.py  # reads 5 emails, saves nothing
```

## Gmail authentication (important)

The server **never opens a browser**. You log in once on your own computer with
`python scripts/gmail_auth.py`; this needs `credentials.json` (OAuth client of type
*Desktop app* from Google Cloud Console, Gmail API enabled). The script writes `token.json`
and prints a one-line `GOOGLE_TOKEN_JSON=...` for Render.

* In Google Cloud Console → OAuth consent screen, set **Publishing status = In production**.
  While it says *Testing*, Google expires the refresh token after **7 days** and sync will
  start returning `503 Gmail authorisation expired`.
* If sync says authorisation expired/revoked, run `gmail_auth.py` again and update `GOOGLE_TOKEN_JSON`.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `MONGODB_URI` | yes | MongoDB Atlas connection string |
| `GEMINI_API_KEY` | yes (else keyword fallback is used) | Google AI Studio key |
| `GOOGLE_TOKEN_JSON` | yes on Render | one-line token JSON from `gmail_auth.py` (locally `token.json` is used) |
| `ALLOWED_ORIGINS` | yes in production | comma-separated frontend URLs, no trailing slash |
| `ENVIRONMENT` | recommended | `production` on Render (hides `/docs`) |
| `API_KEY` | recommended | if set, `/emails/*` needs header `X-API-Key` |
| `MONGODB_DB_NAME`, `GEMINI_MODEL`, `GMAIL_QUERY`, `SYNC_MAX_EMAILS`, `LOG_LEVEL`, ... | no | see `.env.example` |

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/`, `/healthz` | liveness (Render health check) |
| GET | `/status` | database / gmail / gemini configured? |
| GET | `/emails/` | list, newest first (optional `?limit=`) |
| GET | `/emails/high-priority`, `/emails/action-required`, `/emails/category/{category}` | filtered lists |
| GET | `/emails/briefing` | `{"briefing": "..."}` |
| POST | `/emails/sync` | optional `?max_results=1..100`; returns `count` (new emails) + details |
| PATCH | `/emails/{id}/read` | marks read in MongoDB and Gmail |

Errors are always `{"detail": "..."}`: `401` bad API key, `404` unknown email, `422` invalid input,
`502` Gmail problem, `503` MongoDB / Gmail-auth / AI unavailable.

## Deploy on Render

1. Push to GitHub (below). 2. Render → **New + → Web Service** → pick the repo.
3. Settings: **Root Directory** `backend` · **Build** `pip install -r requirements.txt` ·
   **Start** `uvicorn main:app --host 0.0.0.0 --port $PORT` · **Health Check Path** `/healthz`.
   (Or use **New + → Blueprint**, which reads `render.yaml`.)
4. Environment: set the variables in the table above plus `PYTHON_VERSION=3.12.3`.
5. MongoDB Atlas → Network Access: allow Render's IPs (simplest: `0.0.0.0/0` with a strong DB password).
6. Frontend: set `VITE_API_URL=https://<your-service>.onrender.com`, and put the frontend's URL in `ALLOWED_ORIGINS`.

Free Render services sleep when idle; the first request after a pause can take ~30–60 s.
