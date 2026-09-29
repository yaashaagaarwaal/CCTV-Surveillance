import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import cameras, events, health
from app.core.config import settings
from app.db.session import init_db
from app.services.camera.manager import (
    camera_manager,
    init_cameras_from_settings,
    warmup_camera_permissions,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    warmup_camera_permissions(settings.cameras)
    init_cameras_from_settings(settings.cameras)
    camera_manager.start_all()
    yield
    camera_manager.stop_all()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(cameras.router, prefix=settings.api_v1_prefix)
app.include_router(events.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root():
    return {"message": f"{settings.app_name} API is running"}
