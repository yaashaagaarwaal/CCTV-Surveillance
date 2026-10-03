from fastapi import Depends, HTTPException, Request, WebSocket

from app.core.config import settings
from app.security.sessions import AuthUser, lookup_session


def client_ip(connection: Request | WebSocket) -> str:
    """The caller's address. X-Forwarded-For is believed only when explicitly
    configured (behind your own reverse proxy), since anyone can send it."""
    if settings.security.trust_proxy_headers:
        forwarded = connection.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return connection.client.host if connection.client else "unknown"


def session_token(connection: Request | WebSocket) -> str | None:
    return connection.cookies.get(settings.security.cookie_name)


def current_user(request: Request) -> AuthUser:
    """Dependency: the logged-in user, or 401. Put on every route that
    exposes cameras, streams, recordings, events, people or alerts."""
    user = lookup_session(session_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    request.state.user = user
    return user


def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def websocket_user(websocket: WebSocket) -> AuthUser | None:
    return lookup_session(session_token(websocket))
