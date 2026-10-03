import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import alerts, auth, cameras, dashboard, events, health, notifications, people, realtime, sources, zones
from app.core.config import settings
from app.core.shutdown import install_shutdown_hooks
from app.db.session import init_db
from app.security.bootstrap import docs_enabled, ensure_admin, validate_security_config
from app.security.middleware import OriginCheckMiddleware, SecurityHeadersMiddleware
from app.security.sessions import purge_expired_sessions
from app.services.alert_bus import alert_bus
from app.services.camera.manager import camera_manager, warmup_camera_permissions
from app.services.camera.registry import load_enabled_specs, seed_default_camera
from app.services.detection.detector import load_person_detector
from app.services.faces.runtime import set_face_service
from app.services.faces.service import load_face_service
from app.services.notifications.dispatcher import dispatcher
from app.services.recording.recovery import recover_stale_events

logging.basicConfig(level=logging.INFO)

# Fail at boot, with a clear message, rather than run with an unsafe configuration.
validate_security_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    alert_bus.bind_loop(asyncio.get_running_loop())
    install_shutdown_hooks()
    init_db()
    ensure_admin()
    purge_expired_sessions()
    recover_stale_events()
    seed_default_camera()
    dispatcher.start()

    camera_manager.set_person_detector(load_person_detector())
    face_service = load_face_service(settings.face)
    set_face_service(face_service)
    camera_manager.set_face_service(face_service)
    specs = load_enabled_specs()
    warmup_camera_permissions(specs)
    for spec in specs:
        camera_manager.start_camera(spec)

    yield
    camera_manager.stop_all()
    dispatcher.stop()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled() else None,
    redoc_url=None,
    openapi_url="/openapi.json" if docs_enabled() else None,
)

# Middleware runs outermost-last: host check -> security headers -> CORS -> origin check -> app.
app.add_middleware(OriginCheckMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # explicit list only; never "*" (cookies are used)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

prefix = settings.api_v1_prefix
app.include_router(health.router, prefix=prefix)  # public: just "ok", no data
app.include_router(auth.router, prefix=prefix)  # login is public; the rest of it checks the session itself
for protected in (
    auth.users_router,
    cameras.router,
    events.router,
    dashboard.router,
    sources.router,
    people.router,
    alerts.router,
    zones.router,
    notifications.router,
):
    app.include_router(protected, prefix=prefix)  # each router requires a logged-in user
app.include_router(realtime.router, prefix=prefix)  # WebSocket; checks the session cookie itself

_dist = settings.security.frontend_dist.resolve()
if settings.security.serve_frontend and (_dist / "index.html").is_file():
    # Serve the built dashboard from this same server: one origin, one port,
    # so the login cookie never has to cross sites.
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def serve_frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (_dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(_dist):
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})

else:

    @app.get("/")
    def root():
        return {"message": f"{settings.app_name} API is running"}
