# 🛡️ Smart AI-Based CCTV Surveillance System

A modular **AI-powered CCTV surveillance platform** designed for real-time monitoring, intelligent event detection, automated recording, and scalable multi-camera surveillance.

The system combines **computer vision, real-time video processing, event-based recording, and a modern web dashboard** to provide an intelligent surveillance workflow.

---

## ✨ Features

* 📹 **Live CCTV Streaming** — NVR-style tiles with LIVE / REC / person-count overlays
* 📷 **Multi-Camera Support** — webcam, RTSP/IP, HTTP/MJPEG and looping video-file sources, each fully isolated in its own thread
* 🛠️ **Camera Management** — add, edit, enable/disable, test and delete cameras from the dashboard (stored in SQLite, nothing hardcoded)
* 🖥️ **Surveillance Dashboard** — camera grid, active alerts, recent events and recordings, plus Events and Recordings pages with filters, playback, download and delete
* 🏃 **Motion Detection** using OpenCV MOG2
* 🧍 **YOLO Person Detection** — bounding boxes + confidence, on the live feed
* 🙂 **Face Recognition & Unknown-Person Alerts** — register people with photos; each face is labeled known / unknown / not confidently recognized; strangers raise an event, a snapshot and an acknowledgeable alert
* 🎥 **Event-Based Video Recording**
* 🗄️ **SQLite Event History** — motion, person and unknown-person events, with who was recognized
* ▶️ **Video Playback & Download**
* 🟢 **Camera Online/Offline Monitoring**
* 🔄 **Automatic Camera Reconnection**
* ⚡ **Background Camera + AI Processing** — never blocks the live stream
* 🔔 **Alerts** — bell badge, pop-up toasts and an Alerts page (push notifications by email/phone are a future step)

---

## 🧠 AI Surveillance Pipeline

Motion detection gates YOLO (cheap check first, expensive model only when
something is actually happening), and detections feed the same event/
recording system motion already uses:

```text
              CCTV / IP Camera
                     │
                     ▼
             Frame Acquisition
                     │
                     ▼
             Motion Detection        ◄── implemented (OpenCV MOG2)
                (OpenCV)
                     │
              (only while recording,
               every Nth frame)
                     ▼
             YOLO Object Detection   ◄── implemented (YOLOv8n, "person" class only)
                     │
              ┌──────┴──────┐
              │             │
           Person        (ignored —
              │           only "person" is
              │            security-relevant
              │            for now)
              ▼
        Face Detection + Recognition ◄── implemented (YuNet + SFace, per person found)
              │
     ┌────────┼─────────────┐
     │        │             │
   Known   Not sure       Unknown
     │     (small / turned   │
     │      / in between)    │
     ▼        ▼              ▼
 Log who    Log only     Event + snapshot + ALERT
     │        │              │
     └────────┴──────┬───────┘
                     ▼
        Event Database (SQLite)   ◄── implemented (events, face_observations, alerts)
              │
              ▼
        React Dashboard           ◄── implemented (live feed, boxes, event history)
```

---

## 🏗️ System Architecture

```text
 SQLite `cameras` table  ◄──── Camera Management page (REST API)
        │ (loaded at startup, changed live at runtime)
        ▼
 Camera Manager — one worker thread per camera
 (a failing camera only ever affects its own thread)
        │
        ▼
 Motion Detection (OpenCV MOG2, per camera)
        │
        ├── no motion ──► Live MJPEG Stream (raw frame)
        │
        ▼ motion found
 YOLO Person Detection (one shared model, every Nth frame, MPS-accelerated)
        │
        ▼ person found
 Face Detection → Embedding → Match against registered people
        │
        ├──────────────► Live MJPEG Stream (boxes, names, UNKNOWN / NOT SURE)
        │
        ├── unknown (confirmed) ──► Snapshot + Alert
        │
        ▼
 Event Recording (H.264 .mp4)
        │
        ├──────────────► Video Storage (organized by camera/date)
        │
        ▼
 SQLite Event Database (events, person_detections, face_observations, alerts, people)
        │
        ▼
 React Dashboard (live feed, event history, playback)
```

---

## 🛠️ Technology Stack

### Backend

* Python
* FastAPI
* OpenCV
* SQLAlchemy
* SQLite

### Frontend

* React + React Router
* Vite
* Tailwind CSS
* lucide-react icons

### Computer Vision

* OpenCV MOG2 background subtraction (motion detection)
* YOLOv8n via Ultralytics — person detection, MPS-accelerated on Apple Silicon
* YuNet (face detection) + SFace (128-number face embeddings), both run by OpenCV — no extra Python packages

### Storage

* SQLite
* Local MP4/H.264 video storage

---

## 📁 Project Structure

```text
CCTV-Surveillance/
│
├── backend/
│   ├── models/              YOLO weights (auto-downloaded, gitignored)
│   ├── sample_videos/       demo "camera" videos for testing (generated, gitignored)
│   ├── scripts/             make_demo_videos.py
│   ├── app/
│   │   ├── api/                cameras, events, people, alerts, dashboard, sources, health
│   │   ├── core/               settings, shutdown handling
│   │   ├── db/                 cameras, events, people, face_samples, face_observations, alerts ...
│   │   ├── services/
│   │   │   ├── camera/         factory, manager (runtime registry), registry (DB glue)
│   │   │   ├── motion/
│   │   │   ├── detection/      shared YOLOv8 person detector
│   │   │   ├── faces/          face service, event tracker, private storage
│   │   │   └── recording/      motion→YOLO→recording pipeline + crash recovery
│   │   └── main.py
│   └── requirements.txt
│
└── frontend/
    └── src/
        ├── pages/              Dashboard, Cameras, Alerts, Events, Recordings, People
        ├── components/         CameraTile, AlertsPanel, VideoModal, ui/, layout/ ...
        ├── hooks/              usePolling, useCameras
        ├── api.js              backend client
        └── App.jsx             routes
```

---

## 🚀 Getting Started

### Backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

> **First run:** a fresh install adds one "Local Webcam" camera automatically
> (delete or edit it on the Cameras page). macOS will prompt for camera permission — click **Allow**
> (run the backend in a normal foreground terminal the first time so the
> dialog can appear). Startup also takes a few extra seconds while YOLO
> downloads its weights (first run only, ~6 MB) and warms up the model.

---

## 🙂 Face Recognition & Unknown Persons

**How it works.** When YOLO finds a person, the face stage finds faces inside that
person's box (YuNet), turns each face into a 128-number *embedding* (SFace — a neural
network, not a pixel comparison), and compares it with every registered embedding using
cosine similarity. Thresholds turn that score into one of three outcomes:

| Outcome | When | What happens |
|---|---|---|
| **Known** | similarity ≥ `known_threshold` (0.40) | green box with the name; logged once per 30 s |
| **Unknown** | face is clear and frontal enough, and similarity < `unknown_threshold` (0.25) | red box; after 3 confirmations in one recording → `unknown_person` event, snapshot, alert |
| **Not confidently recognized** | similarity in between, face too small (< 48 px), or head turned away | orange "NOT SURE"; logged, **no alert** |

Several faces in one frame are handled independently. Nothing is decided from a single
frame, and alerts are rate-limited to one per camera per minute.

**Registering people** (People page): *Register person*, then either *Add photos*
(JPEG/PNG, one face per photo, front-facing, clear, ≥ 80 px face) or *Use camera* to
capture from a live camera. Use 3+ photos with different angles and lighting. Each photo is
checked and rejected with a reason if it has no face, several faces, a tiny or blurry face,
or a head turned too far. If nobody is registered, no unknown-person alerts are raised
(there is nobody to be unknown *to*).

**Alerts.** Unknown-person alerts are saved in the database with a snapshot and stay on the
dashboard (bell badge, alert panel, toast, Alerts page) until acknowledged. Events show who
was recognized; filter by "Unknown person" on the Events and Recordings pages.

**Privacy & storage.** Everything stays on this computer; nothing is sent anywhere. Uploaded
photos are *not* kept — only the 128-number embedding (in SQLite) and a 200 px face
thumbnail (`backend/app/storage/faces/`). The database file and the `faces/` and
`snapshots/` folders are owner-only (`chmod 600/700`) and git-ignored. Embeddings are not
encrypted at rest, and **the API has no login yet** — anyone who can reach port 8000 can
view and manage face data, so don't expose it to a network until authentication is added.

**Accuracy — please read.** Face recognition is statistical and is *not* 100% accurate.
Lighting, angle, distance, camera quality and resemblance between people all affect it, and
it can both miss a registered person and, rarely, match a stranger. The default thresholds
come from OpenCV's guidance for this model plus a small test (see below), not from a
benchmark on your cameras — tune them on your own setup. Treat results as a helper, not proof
of identity, and don't rely on this system alone for anything safety-critical.

**Tuning.** Edit `FaceConfig` in `backend/app/core/config.py`, or override without editing
code using environment variables (nested with `__`):

```bash
FACE__KNOWN_THRESHOLD=0.45 FACE__UNKNOWN_CONFIRMATIONS=5 uvicorn app.main:app --port 8000
```

| Setting | Default | Effect |
|---|---|---|
| `known_threshold` | 0.40 | Higher = stricter about calling someone known (fewer mistaken matches, more "not sure") |
| `unknown_threshold` | 0.25 | Lower = fewer unknown alerts (a wider "not sure" band) |
| `min_face_px` | 48 | Smaller faces are never called "unknown" |
| `max_yaw_ratio` | 0.4 | How far a head may turn before it's "not sure" |
| `min_detection_score` | 0.8 | Ignore weak face detections (hands, objects) |
| `unknown_confirmations` | 3 | Recognition cycles needed before an unknown alert |
| `alert_cooldown_seconds` | 60 | Minimum gap between alerts per camera |
| `observation_interval_seconds` | 30 | How often the same known person is logged |

The two model files (~39 MB) download to `backend/models/` on first start. If that fails
(e.g. offline), face recognition turns itself off and everything else keeps working. A
recognition error on any frame is contained and never interrupts a camera.

**Testing it yourself.** Register yourself via *Use camera* on a webcam camera, then walk
in front of it: your name should appear on the tile and event. Have someone *unregistered*
walk in: they should be flagged UNKNOWN, an alert should pop up, and the recording should
show as "Unknown person". Without a second person, you can also delete yourself from the
People page and watch yourself become "unknown". Expect to adjust thresholds.

## 📷 Managing Cameras

Open the **Cameras** page. Cameras are stored in SQLite and can be added,
edited, enabled/disabled and deleted while the app runs — no restart, no
code changes.

| Type | Source | Example |
|---|---|---|
| Local webcam | device index | `0` (built-in), `1` (external) |
| RTSP / IP camera | stream URL | `rtsp://user:pass@192.168.1.50:554/stream1` |
| HTTP / MJPEG | stream URL | `http://192.168.1.60:8080/video` |
| Video file (loops) | file in `backend/sample_videos/` | `demo_entrance.mp4` |

* **Test connection** in the form opens the source and grabs one frame before you save.
* Passwords in RTSP/HTTP URLs are masked (`admin:****@…`) everywhere they are displayed.
* **Deleting a camera keeps its events and recordings**; disabling one just stops it.
* A camera that can't connect (unplugged, bad URL, no permission) shows **Offline** and
  retries every few seconds — it never affects the other cameras.
* Only one program can use a webcam at a time, so a second camera pointing at the same
  device index will show Offline.

## 🧪 Testing Multiple Cameras With One Webcam

Generate two demo videos (an empty scene, then real photos of people moving through it):

```bash
cd backend
source venv/bin/activate
python scripts/make_demo_videos.py
```

Then on the **Cameras** page add two cameras of type **Video file (loops)** — for
example "Front Entrance" → `demo_entrance.mp4` and "Street View" → `demo_street.mp4`.
Each runs its own motion detection, YOLO and recording; events and recordings are
filed under the correct camera. Add an RTSP camera with a fake address to see a
failing camera stay isolated.

> Looping videos re-trigger motion on every loop, so they create a steady stream of
> events and recordings. Disable or delete the demo cameras when you're done.

## 🖥️ Dashboard Pages

* **Dashboard** — stat cards, live camera grid (1–4 columns, click ⤢ to expand a tile),
  active alerts (person detected / camera offline), recent events and recordings.
  Up to 4 cameras use live MJPEG streams; additional ones fall back to refreshing
  snapshots, because browsers only allow ~6 simultaneous connections per server.
* **Cameras** — management page described above.
* **Events** — filter by camera, type and status; paginated; play, download, delete.
* **Recordings** — thumbnail grid of saved clips; play, download, delete.

The layout is responsive (sidebar becomes a menu on phones, tables become cards).

## 🔌 REST API

Interactive docs at `http://127.0.0.1:8000/docs`.

| Endpoint | Purpose |
|---|---|
| `GET/POST /api/cameras` | list (with live status) / add a camera |
| `GET/PATCH/DELETE /api/cameras/{id}` | read / edit or enable-disable / remove |
| `POST /api/cameras/test` | try a source without saving it |
| `GET /api/cameras/{id}/stream` | live MJPEG stream |
| `GET /api/cameras/{id}/snapshot` | latest frame as one JPEG |
| `GET /api/events` | filters: `camera_id`, `event_type`, `status`, `recordings_only`, `limit`, `offset` |
| `GET /api/events/{id}/video` · `/download` · `/thumbnail` | playback, file download, preview image |
| `DELETE /api/events/{id}` | delete an event and its recording file |
| `GET /api/dashboard/summary` | counts and active alerts for the dashboard |
| `GET /api/sources/files` | video files usable as a file camera |
| `GET/POST /api/people` · `PATCH/DELETE /api/people/{id}` | registered people |
| `POST /api/people/{id}/faces` · `/faces/from-camera` | register face photos (upload, or capture from a camera) |
| `GET /api/people/status` | whether recognition is running + thresholds |
| `GET /api/alerts` · `POST /api/alerts/{id}/acknowledge` · `/acknowledge-all` | alert list / acknowledge |
| `GET /api/alerts/{id}/snapshot` | the unknown person's snapshot |

## 🛡️ Reliability Notes

* **Camera isolation** — every camera has its own thread, motion detector and recording
  pipeline; errors are caught per camera and the camera simply goes offline and retries.
  Network cameras time out after 5 s instead of hanging.
* **Shared YOLO model** — loaded once and used by all cameras behind a lock (no concurrent
  GPU inference); if it fails to load, motion detection and recording still work.
* **Clean shutdown** — Ctrl+C stops all cameras and finalizes any in-progress recording
  (marked `interrupted`), even while a browser has live streams open.
* **Crash recovery** — if the server is killed mid-recording, those events are closed out
  at the next startup (`interrupted` if the file is readable, otherwise `failed`).

## 🔐 Remote Monitoring (secure architecture)

**Default: local only.** The server listens on `127.0.0.1`, every API route, stream, snapshot,
recording and WebSocket needs a login (cookie session), and nothing is exposed to a network.
An automated test (`python -m tests.test_route_protection`) fails if any route is added
without authentication.

**What protects it:** scrypt-hashed passwords; random session tokens stored only as keyed
hashes; `HttpOnly` + `SameSite=Strict` cookies (`Secure` over HTTPS); login throttling
(5 failures locks that user+address for 5 min); admin/viewer roles enforced on the server;
Host-header allow-list; Origin check on writes and WebSockets (CSRF); explicit CORS origins
(never `*`); security headers; secrets only from environment variables / `backend/.env`.

**Reaching it from outside — choose in this order:**
1. **A private network (recommended):** install Tailscale or WireGuard on the server and your
   phone/laptop, keep uvicorn on `127.0.0.1`, and reach it through the VPN. Nothing is public.
2. **A reverse proxy with HTTPS** (`deploy/Caddyfile.example`): uvicorn stays on `127.0.0.1`;
   Caddy terminates TLS. Only do this on a machine you are prepared to keep patched.
3. Never forward port 8000 straight from your router or bind `0.0.0.0` without a proxy.

**Checklist for option 2:** copy `backend/.env.example` to `backend/.env`; set `REMOTE_MODE=true`,
`ALLOWED_HOSTS`, `CORS_ORIGINS` (https), `PUBLIC_URL`, a 32+ character `SECRET_KEY`, and a strong
`ADMIN_PASSWORD`; build the frontend (`npm run build`) and set `SECURITY__SERVE_FRONTEND=true`
(one origin); set `SECURITY__TRUST_PROXY_HEADERS=true` only behind your proxy. In remote mode the
server **refuses to start** if any of this is unsafe. Manage accounts with
`python scripts/manage_users.py` or the Users page. Face data and recordings are sensitive:
the server has no per-camera permissions, and embeddings are not encrypted at rest.

## 🔔 Alerts, 🌙 Night Mode

**Alerts** (SQLite, severity low/medium/high/critical, unread → read → resolved): unknown person,
person in a restricted zone (draw zones on a camera snapshot; optional schedule), suspicious
activity (simple rules: loitering, after-hours presence — heuristics, not behavior
understanding), and camera offline (one alert per outage; resolves itself when the camera
returns). Delivered live over an authenticated WebSocket, with optional browser notifications
and a pluggable email channel (`EMAIL__*` settings; off by default; failures never affect cameras).

**Night mode** is detected from brightness and colour (low light, or a bright monochrome
infrared feed) and shown as NIGHT MODE / NIGHT · IR. At night, person detection tries both the
raw and a contrast-enhanced copy and keeps whichever finds more people (measured recall:
97% / 83% / 56% in moderate / dark / very dark frames, versus 97% / 82% / 21% raw only).
Enhancement only re-maps detail the camera captured — it cannot recover what darkness removed
and it amplifies noise — so detection at night is less reliable. Recordings and the default
live view are never enhanced (`NIGHT__ENHANCE_LIVE_VIEW=true` opts in, labelled on screen).
`python scripts/make_demo_videos.py` also creates `demo_night.mp4` and `demo_infrared.mp4`.

## ⚙️ YOLO Detection Settings

All in `backend/app/core/config.py`, under `Settings.detection`:

| Setting | Default | Effect |
|---|---|---|
| `enabled` | `true` | Turns person detection on/off. If the model fails to load, this auto-disables per-camera and motion/recording keep working. |
| `confidence_threshold` | `0.5` | Minimum confidence (0–1) to count as a real person. |
| `imgsz` | `320` | Inference resolution — smaller is faster, less precise. |
| `run_every_n_frames` | `5` | YOLO only runs on every Nth frame **while a motion recording is already active** — the main cost control, so the model never runs at all on an idle scene. |
| `model_path` | `backend/models/yolov8n.pt` | Auto-downloaded on first run if missing. |

Restart the backend after changing any of these. One model instance is shared by all cameras. Model inference uses
Apple Silicon's MPS GPU backend automatically when available (falls back to
CPU otherwise) — check the startup log for `YOLO model ready on device=mps`.

## 🔮 Future Enhancements

* 👤 Face recognition
* 🚨 Unknown-person alerts
* 📡 Real-time WebSocket notifications
* 🧠 Suspicious activity detection
* 🌙 Night surveillance
* 🌐 Secure remote monitoring
* 📊 Intelligent event analytics

---

## 🎯 Vision

Build a scalable **AI-powered surveillance platform** that moves beyond traditional CCTV by detecting, understanding, and responding to activities in real time.
