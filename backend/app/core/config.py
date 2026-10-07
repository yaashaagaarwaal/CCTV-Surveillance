from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


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
    # If the picture's average brightness jumps by more than this (0-255) between
    # frames — lights switched, IR-cut filter flipped, camera exposure re-set — that is a
    # lighting event, not movement: the background model is reset instead of raising a
    # motion event. Gradual changes (dusk) never trigger this.
    lighting_jump_threshold: float = 30.0


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


class FaceConfig(BaseModel):
    # Face detection (YuNet) + recognition (SFace), both small neural nets run
    # by OpenCV itself. Model files are downloaded to `models/` on first run.
    enabled: bool = True
    detector_model_path: Path = BASE_DIR / "models" / "face_detection_yunet_2023mar.onnx"
    detector_model_url: str = (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    )
    recognizer_model_path: Path = BASE_DIR / "models" / "face_recognition_sface_2021dec.onnx"
    recognizer_model_url: str = (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    )

    # --- Detection quality -------------------------------------------------
    # Faces the detector scores below this are ignored entirely (YuNet also
    # fires on hands/objects at low scores).
    min_detection_score: float = 0.8
    # A face narrower than this (pixels) is too small to judge reliably: it is
    # reported as "not confidently recognized", never as "unknown".
    min_face_px: int = 48
    # Faces darker than this (mean gray level of the *raw* face region) are too dark to judge:
    # reported as "not confidently recognized", never as "unknown".
    min_face_brightness: float = 40.0
    # How far a face may be turned sideways before it is judged too oblique
    # to recognize (0 = looking straight at the camera). A turned face
    # naturally scores lower, which must not be mistaken for a stranger.
    max_yaw_ratio: float = 0.4

    # --- Recognition thresholds (cosine similarity, -1..1, higher = more alike)
    # >= known_threshold               -> KNOWN
    # <  unknown_threshold             -> UNKNOWN
    # in between, or a poor-quality face -> NOT CONFIDENTLY RECOGNIZED
    # known_threshold is deliberately strict: wrongly calling a stranger
    # "known" is the costly mistake. OpenCV's own guidance for SFace is 0.363.
    # No face recognizer is perfect; tune these on your own cameras/lighting.
    known_threshold: float = 0.40
    unknown_threshold: float = 0.25

    # --- Events & alerts ---------------------------------------------------
    # An unknown person event/alert needs this many separate recognition
    # cycles with an unknown face inside one recording, so one noisy frame
    # can't raise an alarm.
    unknown_confirmations: int = 3
    # Don't log the same known person (or "not recognized" faces) more often.
    observation_interval_seconds: float = 30.0
    # Minimum gap between unknown-person alerts for one camera.
    alert_cooldown_seconds: float = 60.0

    # --- Registration (stricter than live recognition) ---------------------
    enroll_min_face_px: int = 80
    enroll_max_yaw_ratio: float = 0.6
    enroll_min_detection_score: float = 0.85
    enroll_max_images_per_request: int = 10
    enroll_max_image_bytes: int = 8 * 1024 * 1024


class NightConfig(BaseModel):
    """Low-light / infrared handling.

    "Brightness" is the average gray level (0-255) of a downscaled frame,
    smoothed over a few seconds. Night mode switches ON below `enter_brightness`
    and OFF above `exit_brightness` (the gap stops it flickering). A bright
    feed with almost no color is treated as infrared / night-vision, since IR
    cameras are often well lit but monochrome.

    Enhancement (gamma + CLAHE contrast) only re-maps detail the camera
    actually captured. It cannot recover what darkness removed, and it
    amplifies sensor noise, so detection is still less reliable at night.
    Recordings are always saved un-enhanced.
    """

    enabled: bool = True
    enter_brightness: float = 55.0
    exit_brightness: float = 75.0
    # Mean (max - min) across the color channels, 0-255. Real color scenes measured 16-31;
    # a monochrome IR feed ~3 (just codec noise). Below this AND bright enough = infrared.
    infrared_color_spread: float = 8.0
    infrared_min_brightness: float = 20.0
    smoothing: float = 0.02  # per-frame EMA weight; ~2.5 s at 20 fps
    # At night, also run person detection on a contrast-enhanced copy and keep whichever
    # pass (raw or enhanced) finds more people. Costs one extra YOLO pass per cycle.
    enhance_for_detection: bool = True
    # Also enhance what you SEE live. Off by default so the live view stays an honest picture.
    enhance_live_view: bool = False
    gamma: float = 1.6  # >1 brightens shadows
    clahe_clip_limit: float = 3.0
    # Blur frames slightly before motion detection at night (sensor noise otherwise causes false motion).
    motion_denoise: bool = True
    # Person confidence threshold at night (YOLO scores drop in the dark); None = same as day.
    person_confidence: float | None = None
    # Unknown-person confirmations needed at night (faces are less reliable in the dark).
    unknown_confirmations: int = 5


class ActivityConfig(BaseModel):
    """Simple, explainable rules for "suspicious activity". They are
    heuristics, not behavior understanding: what is suspicious depends on context.
    Per-zone limits (loitering, repeated entry) and per-camera security hours
    are stored in the database and edited from the dashboard; the values here
    are server-wide defaults and tuning knobs."""

    # Optional camera-wide rule: one person continuously in view this long (any
    # part of the picture). Off by default; zone loitering is the precise version.
    lingering_enabled: bool = False
    lingering_seconds: float = 60.0
    # Default security hours for cameras that have none set in the dashboard.
    after_hours_enabled: bool = False
    after_hours_start: str = "23:00"
    after_hours_end: str = "05:00"
    suspicious_alert_cooldown_seconds: float = 300.0
    # Restricted zones: detection cycles in a row a person must be inside, alert spacing,
    # and how long a zone must be empty before the person counts as having left it.
    zone_confirmations: int = 2
    zone_alert_cooldown_seconds: float = 120.0
    zone_exit_seconds: float = 4.0

    # Fall-like posture change (off per camera until enabled in the dashboard).
    # Uses only the person's bounding box: upright (tall) -> lying (wide) quickly,
    # and staying down. Ratios are height / width.
    fall_upright_ratio: float = 1.4
    fall_lying_ratio: float = 0.8
    fall_recovered_ratio: float = 1.2
    fall_window_seconds: float = 3.0  # the change must happen within this time
    fall_min_height_drop: float = 0.35  # box must get this much shorter
    fall_confirm_seconds: float = 4.0  # ...and stay down this long
    fall_min_person_height: float = 0.15  # ignore people smaller than this fraction of the frame
    fall_cooldown_seconds: float = 120.0


class AlertConfig(BaseModel):
    # A camera must stay offline this long before an alert is raised (ignores brief blips).
    camera_offline_grace_seconds: float = 20.0


class EmailConfig(BaseModel):
    """Email notifications — OFF until configured. Set via environment
    (e.g. EMAIL__ENABLED=true EMAIL__HOST=smtp.example.com EMAIL__PASSWORD=...);
    the password never belongs in code or git."""

    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_starttls: bool = True
    use_ssl: bool = False
    from_addr: str = ""
    to_addrs: Annotated[list[str], NoDecode] = []
    # Only alerts at or above this severity are emailed.
    min_severity: str = "high"
    # Snapshots can show faces; leave off unless you want them in your mailbox.
    attach_snapshot: bool = False
    subject_prefix: str = "[Smart CCTV]"
    timeout_seconds: float = 15.0

    @field_validator("to_addrs", mode="before")
    @classmethod
    def _split(cls, value):
        return [v.strip() for v in value.split(",") if v.strip()] if isinstance(value, str) else value


class SecurityConfig(BaseModel):
    cookie_name: str = "cctv_session"
    session_hours: float = 12.0  # idle timeout (sliding)
    session_max_days: int = 7  # absolute lifetime
    min_password_length: int = 10
    login_max_failures: int = 5
    login_lockout_seconds: float = 300.0
    # Honor X-Forwarded-For for the client IP. ONLY enable behind a reverse
    # proxy you control; otherwise clients could spoof their address.
    trust_proxy_headers: bool = False
    # Serve the built frontend (frontend/dist) from this server: one origin, one port.
    serve_frontend: bool = False
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"


class Settings(BaseSettings):
    # Any setting can be overridden by environment variable, nested with a
    # double underscore, e.g.  FACE__KNOWN_THRESHOLD=0.45  MOTION__MIN_AREA=5000
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=BASE_DIR / ".env",  # optional; see .env.example. Never commit it.
        extra="ignore",
    )

    app_name: str = "Smart AI CCTV Surveillance"
    api_v1_prefix: str = "/api"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'cctv.db'}"
    storage_dir: Path = BASE_DIR / "app" / "storage"
    recordings_dir_name: str = "recordings"
    faces_dir_name: str = "faces"
    snapshots_dir_name: str = "snapshots"
    capture_fps: int = 20
    # --- Access control & remote monitoring (see docs: "Remote monitoring") ---
    # Secrets come from the environment / .env, never from code.
    # Comma-separated lists work, e.g. CORS_ORIGINS=https://cctv.example.com,http://localhost:5173
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    # Host names this server answers to (Host-header check). Add your public name for remote use.
    allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1", "[::1]"]
    admin_username: str = "admin"
    # Initial admin password, used only when the user table is empty. If unset, a random
    # one is generated and printed once at first start.
    admin_password: str = ""
    # Signs/hashes session tokens. If unset, one is generated into data/.secret_key.
    secret_key: str = ""
    # REMOTE_MODE=true makes the server refuse to start unless the configuration is safe
    # for network exposure (HTTPS-only cookies, explicit hosts, no wildcard CORS, strong
    # admin password, API docs off).
    remote_mode: bool = False
    # Marks the session cookie "Secure" (HTTPS only). Forced on in remote mode.
    cookie_secure: bool = False
    enable_docs: bool = True
    public_url: str = ""  # used for links in email notifications
    # Cameras live in the database and are managed from the dashboard. On a
    # brand-new install (no cameras, no events) one local webcam is added so
    # the app isn't empty on first launch; delete it from the Cameras page.
    seed_default_camera: bool = True
    # "File" cameras may only read videos from this folder (loops forever),
    # which makes it easy to test multiple sources with a single webcam.
    video_sources_dir: Path = BASE_DIR / "sample_videos"
    motion: MotionConfig = MotionConfig()
    detection: DetectionConfig = DetectionConfig()
    face: FaceConfig = FaceConfig()
    night: NightConfig = NightConfig()
    activity: ActivityConfig = ActivityConfig()
    alerts: AlertConfig = AlertConfig()
    email: EmailConfig = EmailConfig()
    security: SecurityConfig = SecurityConfig()

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_csv(cls, value):
        return [v.strip() for v in value.split(",") if v.strip()] if isinstance(value, str) else value


settings = Settings()
