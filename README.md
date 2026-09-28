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
│       │   ├── cameras.py     list/status/MJPEG-stream endpoints
│       │   └── events.py      event history + video playback/download (Phase 3)
│       ├── db/                 SQLAlchemy models + session setup (Phase 3)
│       │   ├── session.py         engine, SessionLocal, init_db()
│       │   └── models.py          Event table
│       ├── services/
│       │   ├── camera/         camera capture (Phase 2)
│       │   │   ├── base.py         BaseCamera interface + CameraStatus enum
│       │   │   ├── opencv_camera.py  OpenCV VideoCapture implementation
│       │   │   └── manager.py        per-camera background thread + registry
│       │   ├── motion/          motion detection (Phase 3)
│       │   │   └── detector.py     MOG2 background-subtraction detector
│       │   └── recording/       event recording (Phase 3)
│       │       ├── pipeline.py     per-camera motion→recording state machine
│       │       ├── writer.py       cv2.VideoWriter wrapper (H.264)
│       │       └── paths.py        organized, timestamped file paths
│       └── storage/
│           └── recordings/       <camera_id>/<date>/<file>.mp4 (gitignored)
└── frontend/                  React 19 + Vite + Tailwind CSS 4
    └── src/
        ├── main.jsx
        ├── App.jsx            dashboard shell
        ├── index.css          Tailwind entry point
        └── components/
            ├── CameraGrid.jsx    polls /api/cameras, lays out CameraCards
            ├── CameraCard.jsx    one camera's live feed + ONLINE/OFFLINE badge
            ├── EventHistory.jsx  polls /api/events, renders the event table
            ├── EventRow.jsx      one event row + status badge
            └── EventPlayerModal.jsx  <video> playback + download link
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

### Motion detection & recording (Phase 3)

```
MotionDetector (per camera)   — cv2.createBackgroundSubtractorMOG2, tuned by
                                 settings.motion.{sensitivity,min_area,warmup_frames}

MotionEventPipeline (per camera) — state machine, driven one frame at a time
                                    from inside CameraWorker's own thread:

   idle --[motion + cooldown elapsed]--> recording --[no motion for
   post_motion_seconds, OR max_recording_seconds reached]--> idle (cooldown starts)

   on start:  open RecordingWriter, INSERT Event(status="recording")
   on finish: close writer, UPDATE Event SET ended_at, status="completed"|"failed"
   on camera loss / app shutdown: close() -> status="interrupted"

/api/events                   — GET, list recent events (filter by camera_id)
/api/events/{id}               — GET, one event's detail
/api/events/{id}/video          — GET, MP4 file (Range-request seekable, downloadable)
```

**Why MOG2 background subtraction instead of comparing consecutive frames:**
naive frame-differencing flags *any* pixel change — including slow lighting
drift, auto-exposure adjustments, or sensor noise — as motion. MOG2 builds
and continuously updates a statistical model of "what the empty scene looks
like" and only flags genuine outliers, which is what actually keeps false
positives down as requested. It also tags shadows separately (gray, value
127) so a moving object's shadow doesn't get double-counted as more motion.

**Why the three required knobs map where they do:**
`sensitivity` → MOG2's `varThreshold` (higher = less sensitive), `min_area`
→ minimum contour size in pixels (filters out small/irrelevant movement like
leaves or a pet), `cooldown_seconds` → minimum gap between the *end* of one
event and the *start* of the next. All three live in one place,
`Settings.motion` in `core/config.py`, applied to every camera — per-camera
overrides would be a natural but currently unneeded extension.

**Why recording runs inside the existing capture thread, not a new one:**
`MotionEventPipeline.process()` is called from `CameraWorker._run` (see
`manager.py`), the same background thread that already does camera I/O and
JPEG encoding for the live stream. That thread is already off FastAPI's
event loop, so this satisfies "use background/threaded processing" without
adding a second thread and the frame-handoff/synchronization complexity that
would come with it. The live stream reads `_latest_jpeg` through a lock from
a completely independent code path, so it is never blocked by motion
detection or video encoding — verified in Testing below by watching the feed
stay live while a recording is in progress.

**Why `avc1` (H.264) and not OpenCV's default `mp4v` fourcc:** this was
tested directly on this Mac before writing any recording code — `mp4v`
writes successfully but produces MPEG-4 Part 2 video that Chrome/Safari's
`<video>` tag cannot play, so recordings would silently save but never be
viewable in the dashboard. `avc1` produces real H.264 here (confirmed by
reading the fourcc back off a written test file), which every modern browser
plays natively. See `services/recording/writer.py` for this.

**Why one continuous file per event instead of frame-by-frame images:** a
single `.mp4` is what "replay" and "download" mean in the requirements, and
`cv2.VideoWriter` handles this directly — no extra muxing step needed.

**Graceful handling of missing/corrupted recordings:** `/api/events/{id}/video`
checks the file exists on disk before serving it and returns a clear 404
(`"Recording file is missing or was deleted"`) instead of crashing or
hanging; the frontend player shows a friendly fallback message on video load
error instead of a broken player. Both were verified by deleting a
recording's file out from under a live event (see Testing below).

## Project phases

- [x] **Phase 1:** project scaffold, health-check API, dashboard shell that
      confirms frontend ↔ backend connectivity.
- [x] **Phase 2:** camera abstraction, OpenCV capture, MJPEG live stream,
      ONLINE/OFFLINE status, multi-camera-ready manager, graceful failure
      handling, clean shutdown.
- [x] **Phase 3 (this delivery):** motion detection (OpenCV MOG2), event-
      triggered recording, SQLite event history, event API, dashboard event
      list with video playback/download.
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

## macOS camera permission (read this before testing Phase 2/3)

The first time the backend opens your webcam, macOS shows a system dialog:
**"Terminal" (or "Python") would like to access the Camera** — you must
click **Allow**. Until you do, `/api/cameras` will correctly report the
camera as `offline` (this is expected, not a bug).

If you don't see the dialog, or accidentally denied it: go to **System
Settings → Privacy & Security → Camera** and enable it for your terminal
app (Terminal/iTerm) or for Python, then restart the backend.

Run the backend **in a normal foreground terminal window** the first time
(not backgrounded/detached) so macOS has a chance to show the prompt.

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

## Testing Phase 2 — camera & live feed

1. Start the backend (see "Running the project" above) in the foreground and
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

## Testing Phase 3 — motion detection & recording

1. Start the backend and frontend, with your webcam granted permission (see
   above) and the dashboard showing your camera as ONLINE.

2. Wave your hand / walk in front of the camera. Within a second or two you
   should see a new row appear in "Recent motion events" with status
   `RECORDING` (the table refreshes every 5s). The live feed keeps playing
   the whole time — recording never freezes or slows the stream.

3. Stay still. After ~5 seconds (`post_motion_seconds`) the row should flip
   to `COMPLETED` with a duration.

4. Click **View** — a modal opens and plays the recorded clip with normal
   video controls (play/pause/seek). Click **Download recording** to save
   the `.mp4` file directly.

5. Check the file landed in an organized, timestamped location:
   ```bash
   find backend/app/storage/recordings -type f
   ```
   Expect something like
   `backend/app/storage/recordings/cam1/2026-09-28/cam1_20260928_140501_a1b2c3d4.mp4`.

6. Check the database directly if you want to see the raw row:
   ```bash
   cd backend && source venv/bin/activate
   python -c "
   from app.db.session import SessionLocal
   from app.db.models import Event
   with SessionLocal() as s:
       for e in s.query(Event).all():
           print(e.id, e.camera_id, e.status, e.timestamp, e.recording_path)
   "
   ```

7. **False-positive check:** sit still for a minute or two with normal
   ambient lighting — you should see no new events. If you *do* get spurious
   events (e.g. from a monitor flickering in frame, or auto-exposure
   hunting), raise `motion.sensitivity` and/or `motion.min_area` in
   `backend/app/core/config.py` (see tuning guide below) and restart.

8. **Missing-recording handling:** delete a recording file from disk while
   its event still exists, then click **View** on that event in a fresh
   page load (or via `curl http://127.0.0.1:8000/api/events/<id>/video`) —
   expect a clean 404 (`"Recording file is missing or was deleted"`), not a
   crash. The dashboard shows "Could not load this recording" instead of a
   broken player.

9. **Clean shutdown mid-recording:** trigger motion, then immediately press
   `Ctrl+C` on the backend while the event is still `RECORDING`. Restart the
   backend and check that event's status — it should be `interrupted`, not
   stuck on `recording` forever.

### Tuning motion detection

All in `backend/app/core/config.py`, under `Settings.motion`:

| Setting | Default | Effect |
|---|---|---|
| `sensitivity` | 30 | Higher = less sensitive (fewer false positives, may miss small motion) |
| `min_area` | 3000 | Higher = ignores smaller moving objects (pixels²) |
| `cooldown_seconds` | 10 | Minimum gap between the end of one event and the start of the next |
| `post_motion_seconds` | 5 | How long to keep recording after motion stops |
| `max_recording_seconds` | 30 | Hard cap on one continuous clip |
| `warmup_frames` | 30 | Frames spent learning the background before detection activates |

Restart the backend after changing any of these.

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

## What was intentionally left out of Phase 1, 2 & 3

No YOLO/person detection, face recognition, or "unknown person" logic yet —
motion detection here reacts to *any* meaningful movement, not specifically
people. Also not implemented yet: WebSocket-pushed real-time alerts (the
dashboard currently discovers new events by polling every 5s, not an
instant push), night-vision-specific handling, and remote-monitoring
polish (those are Phase 4/6/7). Each is a deliberate boundary so this
delivery could be fully tested end-to-end before adding the next layer.
