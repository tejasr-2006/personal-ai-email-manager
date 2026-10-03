# Backend (FastAPI)

```text
backend/
├── main.py                  app setup: CORS, error handlers, startup
├── config/settings.py       ALL configuration, read from environment variables
├── routes/                  HTTP endpoints (email_routes.py, auth_routes.py, health_routes.py)
├── services/
│   ├── gmail_service.py     talks to Gmail (OAuth, pagination, parsing)
│   ├── ai_service.py        Gemini classification + briefing + validation + fallback
│   ├── auth_service.py      login password check + server-side sessions
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
| `AUTH_PASSWORD` | **yes** | the password you type on the login page (12+ characters) |
| `SESSION_SECRET` | **yes** | random, 32+ characters: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ALLOWED_ORIGINS` | **yes** in production | your exact frontend URL, e.g. `https://personal-ai-email-manager.vercel.app` (no trailing slash, never `*`) |
| `ENVIRONMENT` | recommended | `production` on Render (hides `/docs`) |
| `API_KEY` | optional | server-to-server key (`X-API-Key` header) for scripts; the browser never gets it |
| `SESSION_MAX_AGE_SECONDS` | optional | login lifetime, default 86400 (24 h) |
| `MONGODB_DB_NAME`, `GEMINI_MODEL`, `GMAIL_QUERY`, `SYNC_MAX_EMAILS`, `LOG_LEVEL`, ... | no | see `.env.example` |

## API

**Everything except `/`, `/healthz` and `/auth/login|logout` requires a login** (session cookie)
or the server-side `X-API-Key`. Unauthenticated requests get `401`.


| Method | Path | Notes |
|---|---|---|
| GET | `/`, `/healthz` | liveness (Render health check) |
| POST | `/auth/login` | body `{"password": "..."}` → sets the HttpOnly session cookie |
| GET | `/auth/me` | 200 if logged in, else 401 |
| POST | `/auth/logout` | deletes the session on the server and clears the cookie |
| GET | `/status` | database / gmail / gemini configured? (login required) |
| GET | `/emails/` | list, newest first (optional `?limit=`) |
| GET | `/emails/high-priority`, `/emails/action-required`, `/emails/category/{category}` | filtered lists |
| GET | `/emails/briefing` | `{"briefing": "..."}` |
| POST | `/emails/sync` | optional `?max_results=1..100`; returns `count` (new emails) + details |
| PATCH | `/emails/{id}/read` | marks read in MongoDB and Gmail |

Errors are always `{"detail": "..."}`: `401` not logged in / wrong password, `403` request from a foreign origin, `429` too many failed logins, `404` unknown email, `422` invalid input,
`502` Gmail problem, `503` MongoDB / Gmail-auth / AI unavailable.

## How login works (security model)

```text
Browser (Vercel)  --POST /auth/login {password}-->  FastAPI (Render)
                  <--Set-Cookie: eml_session (HttpOnly, Secure, SameSite=None)--
Browser           --GET /emails/ + cookie-------->  FastAPI --> Gmail / MongoDB / Gemini
```

* The password is checked **on the server** against `AUTH_PASSWORD`. Nothing secret exists in the frontend.
* The session is a random 256-bit token in an **HttpOnly** cookie (JavaScript cannot read it, so XSS
  cannot steal it). MongoDB stores only an HMAC hash of it (`sessions` collection, auto-deleted on expiry).
* **Logout** deletes the session on the server. Changing `SESSION_SECRET` logs everyone out.
* Because the production cookie is `SameSite=None` (needed for Vercel → Render), state-changing requests
  are also checked against `ALLOWED_ORIGINS` (CSRF protection), and CORS only allows your own frontend.
* 10 wrong passwords in 15 minutes locks logins for 15 minutes (a global limit: this is a one-user app).
* Gmail token, MongoDB URI, Gemini key, `API_KEY`, `SESSION_SECRET`, `AUTH_PASSWORD` exist only in Render's environment.

**Browser caveat:** `vercel.app` and `onrender.com` are different *sites*, so this cookie is a "third-party"
cookie. Chrome and Firefox accept it, but **Safari (and iPhone browsers) block it by default** and login
will appear to succeed and then fail. The fix is to make the API same-site, either with a custom domain
(`app.yourdomain.com` + `api.yourdomain.com`, then `COOKIE_SAMESITE=lax`) or by proxying through Vercel:
add `frontend/vercel.json`

```json
{ "rewrites": [{ "source": "/api/:path*", "destination": "https://YOUR-BACKEND.onrender.com/:path*" }] }
```

set `VITE_API_URL=/api` on Vercel and `COOKIE_SAMESITE=lax` on Render (keep `ALLOWED_ORIGINS` as your Vercel URL).

## Deploy on Render

1. Push to GitHub (below). 2. Render → **New + → Web Service** → pick the repo.
3. Settings: **Root Directory** `backend` · **Build** `pip install -r requirements.txt` ·
   **Start** `uvicorn main:app --host 0.0.0.0 --port $PORT` · **Health Check Path** `/healthz`.
   (Or use **New + → Blueprint**, which reads `render.yaml`.)
4. Environment: set the variables in the table above (at least `MONGODB_URI`, `GEMINI_API_KEY`, `GOOGLE_TOKEN_JSON`,
   `AUTH_PASSWORD`, `SESSION_SECRET`, `ALLOWED_ORIGINS`, `ENVIRONMENT=production`) plus `PYTHON_VERSION=3.12.3`.
5. MongoDB Atlas → Network Access: allow Render's IPs (simplest: `0.0.0.0/0` with a strong DB password).
6. Vercel: the **only** variable is `VITE_API_URL=https://<your-service>.onrender.com` (no key, no secret). Then redeploy.

Free Render services sleep when idle; the first request after a pause can take ~30–60 s.
