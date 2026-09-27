# Smart AI-Based Home CCTV Surveillance System

College 3rd-year project. A modular home surveillance system: FastAPI backend
(camera capture, detection, storage, alerts) + React/Vite/Tailwind dashboard
frontend.

## Architecture

```
CCTV Surveillance/
├── backend/                   Python / FastAPI
│   ├── venv/                  virtualenv (Python 3.12, gitignored)
│   ├── requirements.txt
│   ├── data/                  SQLite database file lives here
│   └── app/
│       ├── main.py            FastAPI app entrypoint, CORS, router registration
│       ├── core/
│       │   └── config.py      central settings (DB path, storage path, CORS)
│       ├── api/                route handlers, one router module per feature
│       │   ├── health.py
│       │   └── cameras.py     list/status/MJPEG-stream endpoints
│       ├── db/                 SQLAlchemy models + session setup (added in Phase 3)
│       ├── services/
│       │   └── camera/         camera capture (Phase 2)
│       │       ├── base.py         BaseCamera interface + CameraStatus enum
│       │       ├── opencv_camera.py  OpenCV VideoCapture implementation
│       │       └── manager.py        per-camera background thread + registry
│       └── storage/              recorded video clips + snapshots (gitignored)
└── frontend/                  React 19 + Vite + Tailwind CSS 4
    └── src/
        ├── main.jsx
        ├── App.jsx            dashboard shell
        ├── index.css          Tailwind entry point
        └── components/
            ├── CameraGrid.jsx   polls /api/cameras, lays out CameraCards
            └── CameraCard.jsx   one camera's live feed + ONLINE/OFFLINE badge
```

**Why this shape:** `api/` (routing) is kept separate from `services/`
(business logic / OpenCV / YOLO) so the detection and camera code can be
tested and reused without pulling in FastAPI. `core/config.py` centralizes
settings so every later phase (camera URLs, model paths, alert thresholds)
has one place to configure. The frontend talks to the backend only through
`/api/*`, proxied by Vite in dev — no CORS headaches, and it's a straight
swap to a real reverse proxy in production.

**Why SQLite + local disk:** this is a single-machine home system, not a
distributed one. SQLite needs no server to install/manage, and local disk is
where video clips already have to live for a Mac-based setup. Both are
explicitly named in the project brief and are the right fit for the scale of
a college project.

### Camera module (Phase 2)

```
BaseCamera (abstract)             — open() / read() / is_opened() / release()
   └── OpenCVCamera                — cv2.VideoCapture; source is int (webcam
                                      index) or str (rtsp://.../http://...)

CameraWorker                      — owns ONE camera's background thread:
                                      continuously opens/reads/retries,
                                      JPEG-encodes each frame, stores only
                                      the latest one behind a lock
CameraManager                     — dict[camera_id -> CameraWorker], the
                                      whole multi-camera registry

/api/cameras                      — GET, lists every camera + status
/api/cameras/{id}/status          — GET, one camera's status
/api/cameras/{id}/stream          — GET, MJPEG multipart stream
```

**Why one `OpenCVCamera` class covers webcam *and* future IP cameras:**
`cv2.VideoCapture` accepts either an integer device index or an RTSP/HTTP
URL string transparently. So "prepare for IP cameras later" doesn't need a
second class yet — it needs a `CameraConfig.source` that's a string instead
of `0`. `BaseCamera` still exists as a real interface (not just this one
class) so a genuinely different backend (e.g. an ONVIF SDK, or a cloud
camera API) can be added later without touching `CameraWorker` or the API
layer at all.

**Why a background thread per camera:** `cap.read()` is a blocking call —
on real hardware or a flaky RTSP link it can hang for seconds. Running it on
FastAPI's event loop would freeze every other request while any one camera
was slow. Each camera gets its own thread instead, so:
- one camera hanging or failing never blocks another camera or the API
- the capture loop can retry forever on failure without crashing anything
- multiple browser tabs hitting `/stream` all read the same in-memory latest
  frame instead of each opening a second competing `VideoCapture` on the
  same device (which would fail or fight over the hardware)

**Why MJPEG over `<img>` instead of WebSocket/WebRTC:** an `<img
src="/api/cameras/cam1/stream">` tag natively understands
`multipart/x-mixed-replace` and just keeps repainting — zero frontend
plumbing, no reconnect logic to write. WebRTC would give lower latency but
is a large jump in complexity for a college project; this is the standard
"good enough" approach for a local dashboard.

**Graceful failure, by design:** a camera that fails to open (unplugged, no
OS permission, bad RTSP URL) is reported as `offline` and retried every 3s
forever — it never raises past the worker thread, so it can't crash the
FastAPI process or take other cameras down with it. This was verified by
literally running it with camera access denied (see Testing section below).

## Project phases

- [x] **Phase 1:** project scaffold, health-check API, dashboard shell that
      confirms frontend ↔ backend connectivity.
- [x] **Phase 2 (this delivery):** camera abstraction, OpenCV capture,
      MJPEG live stream, ONLINE/OFFLINE status, multi-camera-ready manager,
      graceful failure handling, clean shutdown.
- [ ] Phase 3: motion detection, event history, SQLite persistence
- [ ] Phase 4: YOLO person detection
- [ ] Phase 5: recording on event, video storage/playback
- [ ] Phase 6: face recognition + unknown-person alerts
- [ ] Phase 7: real-time alerts (WebSocket push to dashboard), night mode, suspicious-activity heuristics, remote monitoring polish

We build and verify one phase at a time before moving to the next.

## Prerequisites

- macOS (Apple Silicon)
- [Homebrew](https://brew.sh) Python 3.12: `brew install python@3.12`
- Node.js 20+ (you have v24, that's fine)

## Setup

### Backend

```bash
cd "backend"
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd "frontend"
npm install
```

## Running the project

Open two terminals.

**Terminal 1 — backend:**

```bash
cd "backend"
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**

```bash
cd "frontend"
npm run dev
```

Then open the URL Vite prints (default http://localhost:5173).

## macOS camera permission (read this before testing Phase 2)

The first time the backend opens your webcam, macOS shows a system dialog:
**"Terminal" (or "Python") would like to access the Camera** — you must
click **Allow**. Until you do, `/api/cameras` will correctly report the
camera as `offline` (this is expected, not a bug).

If you don't see the dialog, or accidentally denied it: go to **System
Settings → Privacy & Security → Camera** and enable it for your terminal
app (Terminal/iTerm) or for Python, then restart the backend.

Run the backend **in a normal foreground terminal window** the first time
(not backgrounded/detached) so macOS has a chance to show the prompt.

## Testing Phase 2 — camera & live feed

1. Start the backend (see "Running the project" below) in the foreground and
   watch for the camera permission dialog on first run — click Allow.

2. Check camera status:
   ```bash
   curl http://127.0.0.1:8000/api/cameras
   ```
   Expect `[{"id":"cam1","name":"Local Webcam","status":"online"}]` once
   permission is granted and the webcam is free (not in use by another app
   like FaceTime/Zoom). Status is `"connecting"` briefly on startup and
   `"offline"` if the camera can't be opened.

3. View the raw MJPEG stream directly in a browser tab:
   `http://127.0.0.1:8000/api/cameras/cam1/stream` — you should see your
   live webcam feed refreshing continuously.

4. Full dashboard: start the frontend too, open it in a browser. You should
   see a camera card with a green "ONLINE" badge and your live feed. Close
   your laptop lid or unplug an external webcam — the badge should turn red
   ("OFFLINE") within ~3 seconds without the dashboard crashing or needing a
   page reload; reconnect it and it should recover on its own.

5. Confirm graceful shutdown: press `Ctrl+C` on the backend terminal. It
   should print `Application shutdown complete` and exit immediately — no
   hanging process, no need to force-kill it.

**What "one failed camera can't crash the backend" looks like in practice:**
if you set `source` to a bad value (e.g. a nonexistent RTSP URL) in
`backend/app/core/config.py`, that camera just reports `offline`/`connecting`
forever while every other camera and the rest of the API keep working
normally — verified during development by running a real webcam and a
fake/unreachable RTSP camera side by side.

## Testing Phase 1

1. Backend health check directly:
   ```bash
   curl http://127.0.0.1:8000/api/health
   ```
   Expect: `{"status":"ok","service":"cctv-backend"}`

2. Interactive API docs: open http://127.0.0.1:8000/docs in a browser —
   FastAPI's auto-generated Swagger UI, should list the `/api/health` route.

3. Dashboard: open the frontend URL. You should see "Smart AI CCTV
   Surveillance" header and a "Backend status: ok" card with a green dot.
   If the backend isn't running, it shows a red dot and "backend
   unreachable" instead — that's the expected failure mode, not a bug.

4. Production build check:
   ```bash
   cd "frontend"
   npm run build
   ```
   Should complete with no errors and produce a `dist/` folder.

## Adding a second camera (already supported)

Edit the `cameras` list in [`backend/app/core/config.py`](backend/app/core/config.py):

```python
cameras: list[CameraConfig] = [
    CameraConfig(id="cam1", name="Local Webcam", source=0),
    CameraConfig(id="cam2", name="Front Door", source="rtsp://user:pass@192.168.1.50:554/stream1"),
]
```

Restart the backend — the dashboard automatically shows a card per camera
(`CameraGrid` renders one `CameraCard` per entry from `/api/cameras`), no
frontend changes needed.

## What was intentionally left out of Phase 1 & 2

No motion detection, YOLO, face recognition, recording, or database models
yet — those are Phase 3+. Adding them now would mean testing multiple new
moving parts at once instead of verifying each layer works before building
on it. Also not implemented yet: WebSocket-based alerts and night-vision
handling (Phase 7).
