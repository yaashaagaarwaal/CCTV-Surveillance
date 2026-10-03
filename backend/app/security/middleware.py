import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1")
    return None


def allowed_origins(scope: Scope) -> set[str]:
    """Origins allowed to make state-changing / WebSocket requests: the
    configured CORS origins, plus this server's own origin (for the case where
    the built frontend is served from it)."""
    origins = set(settings.cors_origins)
    host = _header(scope, b"host")
    if host:
        scheme = scope.get("scheme", "http")
        if settings.security.trust_proxy_headers:
            scheme = _header(scope, b"x-forwarded-proto") or scheme
        scheme = {"ws": "http", "wss": "https"}.get(scheme, scheme)
        origins.add(f"{scheme}://{host}")
    return origins


class OriginCheckMiddleware:
    """CSRF / cross-site WebSocket defense, on top of SameSite=Strict cookies.

    A browser always sends an Origin header on cross-site POST/PATCH/DELETE
    and on WebSocket handshakes. If it names an origin we don't recognize the
    request is refused. Non-browser clients (curl, scripts) send no Origin and
    are not a CSRF vector, so they pass (they still need a valid session).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            origin = _header(scope, b"origin")
            cross_site = _header(scope, b"sec-fetch-site") == "cross-site"
            if (origin and origin not in allowed_origins(scope)) or (cross_site and not origin):
                body = json.dumps({"detail": "Cross-site request refused"}).encode()
                await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        elif scope["type"] == "websocket":
            origin = _header(scope, b"origin")
            if origin and origin not in allowed_origins(scope):
                await receive()  # consume websocket.connect
                await send({"type": "websocket.close", "code": 1008})
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Adds defensive headers to every response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.base = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
            (b"cross-origin-resource-policy", b"same-origin"),
        ]
        if settings.remote_mode:
            self.base.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        if settings.security.serve_frontend:
            self.base.append(
                (
                    b"content-security-policy",
                    b"default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
                    b"style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'none'",
                )
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message["headers"])
                present = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in self.base if k not in present]
                if is_api and b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
