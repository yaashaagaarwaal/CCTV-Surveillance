from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class CameraConfig(BaseModel):
    id: str
    name: str
    # 0/1/... for a local webcam index, or an "rtsp://..." / "http://..."
    # URL string for an IP camera later — OpenCVCamera accepts either.
    source: int | str


class Settings(BaseSettings):
    app_name: str = "Smart AI CCTV Surveillance"
    api_v1_prefix: str = "/api"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'cctv.db'}"
    storage_dir: Path = BASE_DIR / "app" / "storage"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cameras: list[CameraConfig] = [
        CameraConfig(id="cam1", name="Local Webcam", source=0),
    ]


settings = Settings()
