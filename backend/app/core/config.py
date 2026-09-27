from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "Smart AI CCTV Surveillance"
    api_v1_prefix: str = "/api"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'cctv.db'}"
    storage_dir: Path = BASE_DIR / "app" / "storage"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


settings = Settings()
