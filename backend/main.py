"""
Personal AI Email Manager - FastAPI backend.

Run locally:   uvicorn main:app --reload
Run on Render: uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from config.settings import settings
from routes.email_routes import router as email_router
from routes.health_routes import router as health_router
from services import gmail_service, mongodb_service
from services.ai_service import AIServiceError
from services.gmail_service import GmailAPIError, GmailAuthError
from services.mongodb_service import DatabaseUnavailable
from utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger("main")


# ============================================================
# STARTUP / SHUTDOWN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Personal AI Email Manager (environment=%s)", settings.ENVIRONMENT)

    if not settings.MONGODB_URI:
        logger.warning("MONGODB_URI is not set - email endpoints will return 503.")
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set - emails will use the keyword fallback classifier.")
    if not gmail_service.is_configured():
        logger.warning("Gmail is not authorised - run `python scripts/gmail_auth.py` (see README).")
    if not settings.API_KEY:
        logger.warning("API_KEY is not set - the email API is open to anyone who can reach it.")
    if settings.is_production and not getattr(settings, "_origins_were_set", False):
        logger.warning("ALLOWED_ORIGINS is not set in production - only localhost origins are allowed.")

    # Try to connect now so problems show up in the logs immediately,
    # but never crash the server if MongoDB is temporarily down.
    if settings.MONGODB_URI:
        try:
            await asyncio.to_thread(mongodb_service.get_collection)
            logger.info("MongoDB connection OK.")
        except DatabaseUnavailable:
            logger.error("MongoDB is not reachable right now; will retry on the next request.")

    yield

    mongodb_service.close_client()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Personal AI Email Manager",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)


# ============================================================
# MIDDLEWARE
# (the LAST one added is the OUTERMOST, so CORS wraps everything
#  and even error responses carry CORS headers)
# ============================================================

@app.middleware("http")
async def catch_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


# ============================================================
# ERROR HANDLERS  (always JSON: {"detail": "..."})
# ============================================================

def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return _error(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Short human-readable message; never echo the submitted values back.
    problems = [
        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
    ]
    return _error(422, "Invalid request: " + "; ".join(problems))


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable_handler(request: Request, exc: DatabaseUnavailable):
    return _error(503, str(exc))


@app.exception_handler(GmailAuthError)
async def gmail_auth_handler(request: Request, exc: GmailAuthError):
    return _error(503, str(exc))


@app.exception_handler(GmailAPIError)
async def gmail_api_handler(request: Request, exc: GmailAPIError):
    return _error(502, str(exc))


@app.exception_handler(AIServiceError)
async def ai_service_handler(request: Request, exc: AIServiceError):
    return _error(503, f"AI service unavailable: {exc}")


# ============================================================
# ROUTES
# ============================================================

app.include_router(health_router)   # GET /, /healthz, /status
app.include_router(email_router)    # /emails/...


if __name__ == "__main__":  # `python main.py` convenience
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT)
