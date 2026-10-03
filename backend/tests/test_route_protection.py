"""Guards against the classic security regression: a new endpoint added
without authentication. Walks every route of the real app and checks it.

Run:  python -m tests.test_route_protection      (or with pytest)
"""
import os
import sys
import tempfile

# Import the app against a throwaway database so the test never touches real data.
_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("STORAGE_DIR", f"{_tmp}/storage")

from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: E402

from app.main import app  # noqa: E402
from app.security.deps import current_user, require_admin  # noqa: E402

PUBLIC = {  # intentionally reachable without logging in
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),  # only clears the caller's own cookie
}
VIEWER_MAY_WRITE = {  # state changes a read-only viewer is allowed to make
    ("POST", "/api/auth/change-password"),  # their own password
    ("POST", "/api/alerts/read-all"),
    ("POST", "/api/alerts/{alert_id}/read"),
    ("POST", "/api/alerts/{alert_id}/resolve"),
}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _dependency_calls(route: APIRoute) -> set:
    calls, stack = set(), list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        calls.add(dep.call)
        stack.extend(dep.dependencies)
    return calls


def _api_routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route


def test_every_api_route_requires_login_unless_public():
    unprotected = [
        f"{method} {route.path}"
        for method, route in _api_routes()
        if (method, route.path) not in PUBLIC and current_user not in _dependency_calls(route)
    ]
    assert not unprotected, f"routes reachable without authentication: {unprotected}"


def test_write_routes_require_admin_unless_viewer_allowed():
    open_writes = [
        f"{method} {route.path}"
        for method, route in _api_routes()
        if method in WRITE_METHODS
        and (method, route.path) not in PUBLIC | VIEWER_MAY_WRITE
        and require_admin not in _dependency_calls(route)
    ]
    assert not open_writes, f"write routes a viewer could call: {open_writes}"


def test_websocket_routes_are_known():
    sockets = [r.path for r in app.routes if isinstance(r, APIWebSocketRoute)]
    # Each WebSocket authenticates inside its handler (see api/realtime.py); a new one must be reviewed.
    assert sockets == ["/api/ws/alerts"], f"unreviewed WebSocket routes: {sockets}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_")):
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    total = sum(1 for _ in _api_routes())
    print(f"({total} method/route combinations inspected)")
    sys.exit(1 if failures else 0)
