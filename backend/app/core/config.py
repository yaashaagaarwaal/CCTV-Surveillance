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


class MotionConfig(BaseModel):
    # OpenCV MOG2's varThreshold. Higher = a bigger pixel change is needed
    # before something counts as foreground, i.e. LESS sensitive and fewer
    # false positives from lighting flicker/camera noise. OpenCV's own
    # default is 16; home-webcam noise usually needs it higher than that.
    sensitivity: int = 30
    # Minimum contour area (in pixels) to count as real motion rather than
    # noise speckle. Tune this up if small irrelevant movement (a curtain,
    # a pet) keeps triggering events.
    min_area: int = 3000
    # Minimum seconds between the end of one event and the start of the
    # next, so intermittent motion right after a clip ends doesn't spam
    # a new event immediately.
    cooldown_seconds: float = 10.0
    # Keep recording this long after motion is last seen before finalizing
    # the clip, so a recording doesn't cut off mid-action.
    post_motion_seconds: float = 5.0
    # Hard cap on one continuous recording, so nonstop motion (e.g. someone
    # working at a desk) can't grow into one endless file.
    max_recording_seconds: float = 30.0
    # Frames spent letting the background model learn the scene before
    # motion detection activates — without this, the first frame or two
    # look like 100% foreground and falsely trigger an event on startup.
    warmup_frames: int = 30


class DetectionConfig(BaseModel):
    enabled: bool = True
    # yolov8n = "nano", the smallest/fastest YOLOv8 model — right fit for
    # running alongside live capture on a laptop CPU/GPU rather than a
    # dedicated inference server. Auto-downloaded to `model_path` on first
    # run if not already present.
    model_path: Path = BASE_DIR / "models" / "yolov8n.pt"
    # Minimum confidence (0-1) for a detection to count as a real person.
    confidence_threshold: float = 0.5
    # Inference resolution. Smaller = faster but less accurate; 320 is a
    # good speed/accuracy trade-off for a person standing in webcam framing
    # distance (YOLOv8's own default is 640).
    imgsz: int = 320
    # Only run YOLO on every Nth frame *while a motion recording is already
    # active* (see MotionEventPipeline) — this is the main cost control:
    # the expensive model never runs at all while the scene is idle, and
    # even during a recording it isn't run on every single frame.
    run_every_n_frames: int = 5


class Settings(BaseSettings):
    app_name: str = "Smart AI CCTV Surveillance"
    api_v1_prefix: str = "/api"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'cctv.db'}"
    storage_dir: Path = BASE_DIR / "app" / "storage"
    recordings_dir_name: str = "recordings"
    capture_fps: int = 20
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cameras: list[CameraConfig] = [
        CameraConfig(id="cam1", name="Local Webcam", source=0),
    ]
    motion: MotionConfig = MotionConfig()
    detection: DetectionConfig = DetectionConfig()


settings = Settings()
