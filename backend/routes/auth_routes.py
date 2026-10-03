"""
Authentication endpoints:

    POST /auth/login    {"password": "..."}  -> sets the HttpOnly session cookie
    GET  /auth/me                            -> 200 if logged in, else 401
    POST /auth/logout                        -> deletes the session + cookie
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from config.settings import settings
from models.auth import AuthStatus, LoginRequest
from models.email import MessageResponse
from services import auth_service
from utils.logger import get_logger
from utils.security import enforce_origin, require_session

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _cookie_options() -> dict:
    return {
        "key": settings.SESSION_COOKIE_NAME,
        "path": "/",
        "httponly": True,                       # JavaScript cannot read it
        "secure": settings.COOKIE_SECURE,       # HTTPS only (always on in production)
        "samesite": settings.COOKIE_SAMESITE,
    }


@router.post("/login", response_model=AuthStatus)
def login(body: LoginRequest, request: Request, response: Response):
    enforce_origin(request)

    if not settings.auth_configured:
        logger.error("Login attempted but AUTH_PASSWORD / SESSION_SECRET are not configured.")
        raise HTTPException(503, "Authentication is not configured on the server.")

    wait = auth_service.lockout_seconds_remaining()
    if wait:
        raise HTTPException(
            429,
            f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    if not auth_service.verify_password(body.password):
        auth_service.record_failed_login()
        logger.warning("Failed login attempt.")       # never log the password itself
        raise HTTPException(401, "Incorrect password.")

    auth_service.clear_failed_logins()
    token, expires_at = auth_service.create_session()   # new random token every login
    response.set_cookie(
        value=token, max_age=settings.SESSION_MAX_AGE_SECONDS, **_cookie_options()
    )
    logger.info("Login successful.")
    return {"authenticated": True, "expires_at": expires_at.isoformat(timespec="seconds") + "Z"}


@router.get("/me", response_model=AuthStatus, dependencies=[Depends(require_session)])
def me(request: Request):
    expires_at = auth_service.validate_session(request.cookies.get(settings.SESSION_COOKIE_NAME))
    return {
        "authenticated": True,
        "expires_at": expires_at.isoformat(timespec="seconds") + "Z" if expires_at else None,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response):
    enforce_origin(request)
    auth_service.delete_session(request.cookies.get(settings.SESSION_COOKIE_NAME))
    response.delete_cookie(**_cookie_options())    # must repeat the same attributes
    return {"message": "Logged out"}
