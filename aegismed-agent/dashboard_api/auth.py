"""Access control for the dashboard API.

One shared access code (``AEGISMED_ACCESS_CODE``) protects every data endpoint.
Signing in trades the code for a signed, HttpOnly session cookie, so the code is
never kept in the browser. Sessions are signed with the access code itself, so
changing the code signs everyone out.

Behaviour by environment:

* Hosted (``VERCEL`` or ``K_SERVICE`` is set): sign-in is required. If no access
  code is configured the API refuses to serve data (503) rather than run open.
* Local development: sign-in is required only when an access code is set.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Request, Response

COOKIE_NAME = "aegismed_session"
SESSION_SECONDS = 12 * 60 * 60

# Reachable without a session: they are how a session is created, ended or checked.
PUBLIC_API_PATHS = frozenset({"/api/login", "/api/logout", "/api/session"})

LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 15 * 60


def access_code() -> Optional[str]:
    return os.environ.get("AEGISMED_ACCESS_CODE") or None


def is_hosted() -> bool:
    return bool(os.environ.get("VERCEL") or os.environ.get("K_SERVICE"))


def auth_required() -> bool:
    return bool(access_code()) or is_hosted()


def _signature(code: str, expires: int) -> str:
    return hmac.new(code.encode(), f"aegismed-session:{expires}".encode(), hashlib.sha256).hexdigest()


def make_token(code: str, now: Optional[float] = None) -> str:
    expires = int((now if now is not None else time.time()) + SESSION_SECONDS)
    return f"{expires}.{_signature(code, expires)}"


def token_is_valid(token: Optional[str], code: Optional[str], now: Optional[float] = None) -> bool:
    if not token or not code:
        return False
    expires_text, _, signature = token.partition(".")
    if not expires_text.isdigit() or not signature:
        return False
    expires = int(expires_text)
    if expires <= (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(signature, _signature(code, expires))


def code_matches(submitted: str, code: str) -> bool:
    """Constant-time comparison of the submitted code with the real one."""
    return hmac.compare_digest(hashlib.sha256(submitted.encode()).digest(), hashlib.sha256(code.encode()).digest())


def is_signed_in(request: Request) -> bool:
    return token_is_valid(request.cookies.get(COOKIE_NAME), access_code())


def client_id(request: Request) -> str:
    """Best-effort client address for rate limiting.

    Vercel sets these headers itself; elsewhere they may be absent, in which case
    the socket address is used.
    """
    forwarded = request.headers.get("x-vercel-forwarded-for") or request.headers.get("x-forwarded-for") or ""
    first = forwarded.split(",")[0].strip()
    return first or request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _is_https(request: Request) -> bool:
    return (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"


def set_session_cookie(response: Response, request: Request, code: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_token(code),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=_is_https(request),
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
