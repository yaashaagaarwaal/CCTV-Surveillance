# 🛡️ Smart AI-Based Home CCTV Surveillance System

A home CCTV platform that watches several cameras at once, records only when something happens,
recognizes **people** and **faces**, raises **alerts** for unknown people, restricted-area
intrusions and other explainable security events, keeps working at **night**, and can be reached
**remotely and securely** — all running on your own computer, with no cloud.

> 3rd-year college project. Backend: Python · FastAPI · OpenCV · YOLOv8 · SQLite.
> Frontend: React · Vite · Tailwind CSS.

| | |
|---|---|
| 📖 Presentation content | [docs/PRESENTATION.md](docs/PRESENTATION.md) |
| 🎤 Viva questions & answers | [docs/VIVA.md](docs/VIVA.md) |
| ▶️ 4-minute demo script | [docs/DEMO.md](docs/DEMO.md) |

---

## Contents

1. [Features](#-features) · 2. [Architecture](#-architecture) · 3. [Technology stack](#-technology-stack) ·
4. [Project structure](#-project-structure) · 5. [Installation](#-installation) · 6. [Usage guide](#-usage-guide) ·
7. [Configuration](#-configuration) · 8. [API documentation](#-api-documentation) ·
9. [Database schema](#-database-schema) · 10. [How the AI works](#-how-the-ai-works) ·
11. [Security & remote monitoring](#-security--remote-monitoring) · 12. [Testing & results](#-testing--results) ·
13. [Known limitations](#-known-limitations) · 14. [Future improvements](#-future-improvements) · 15. [Troubleshooting](#-troubleshooting)

---

## ✨ Features

| Area | What it does |
|---|---|
| 📹 **Live CCTV** | NVR-style tiles with LIVE / REC / person-count badges, live MJPEG streaming, expandable tiles |
| 📷 **Multiple cameras** | Webcam, RTSP/IP, HTTP/MJPEG and looping video-file sources; each camera runs in its own thread, so one failing camera never affects the others. Cameras are added, edited, tested, enabled/disabled and deleted from the dashboard — no restart |
| 🏃 **Motion detection** | OpenCV MOG2 background subtraction with noise/shadow filtering; lighting changes are not mistaken for movement |
| 🧍 **YOLO person detection** | YOLOv8n finds people (bounding box + confidence), only while motion is happening — cheap check first, expensive model second |
| 🎥 **Event recording** | H.264 MP4 clips of the raw video, organized by camera and date, with seeking, download and delete; crash-safe |
| 🗂️ **Event history** | Every motion / person / unknown-person / restricted-area / suspicious event in SQLite, filterable, paginated, with who was recognized and *why* it was flagged |
| 🙂 **Face recognition** | Register people with photos or the webcam; faces are labelled *known*, *unknown* or *not sure* (never guesses when the face is small, dark or turned away) |
| 🚨 **Unknown-person detection** | A confirmed stranger creates an event, a snapshot and an alert |
| 🔔 **Alert system** | Types: unknown person, restricted area, suspicious activity, camera offline. Severity (low → critical), timestamps, unread → read → resolved lifecycle, real-time delivery over WebSocket, toasts, browser notifications, optional email (off by default, pluggable) |
| 🕵️ **Suspicious-activity rules** | Restricted-zone intrusion, loitering in a zone, repeated entry, unusual (security) hours, and an experimental fall-like rule. Plain rules, each alert states *which* rule fired and *with what numbers* |
| 🌙 **Night surveillance** | Detects low light and infrared video automatically, shows **NIGHT MODE**, keeps person detection working (dual raw/enhanced pass). Recordings are never altered |
| 🔐 **Authentication** | Login with hashed passwords, server-side sessions, admin / viewer roles, login throttling; every API route, stream, snapshot and recording is protected |
| 🌐 **Secure remote architecture** | Safe-by-default local server; documented VPN / reverse-proxy deployment; a `REMOTE_MODE` that refuses to start with an unsafe configuration |
| 🛠️ **Reliability** | Auto-reconnect, clean Ctrl+C shutdown, crash recovery of half-written recordings, contained failures (a face-model crash never stops recording) |

Everything runs locally. No video, face data or alert leaves your computer unless you configure email.

---

## 🏗️ Architecture

```text
                       ┌──────────────────────────── React dashboard (browser) ───────────────────────────┐
                       │  Dashboard · Cameras · Events · Recordings · Alerts · People · Users             │
                       └───────────────▲──────────────────────────────▲───────────────────────────────────┘
                REST + MJPEG streams   │ (cookie session)             │ WebSocket (live alerts)
                       ┌───────────────┴──────────────────────────────┴───────────────────────────────────┐
                       │                        FastAPI backend  (Python)                                 │
                       │  security middleware: Host check → headers → CORS → Origin/CSRF → login required │
                       │  routers: auth · cameras · events · people · alerts · zones/rules · dashboard    │
                       └───────────────▲──────────────────────────────────────────────────────────────────┘
                                       │ in-process
              ┌────────────────────────┴────────────────────────────┐
              │ CameraManager — one worker THREAD per camera        │      ┌──────────────────────────┐
              │                                                     │      │ SQLite (cctv.db)         │
              │  frame ─► Lighting analysis (day / night / IR)      │      │ cameras, events, alerts, │
              │       ─► Motion detection (OpenCV MOG2)             │ ───► │ people, face_*, zones,   │
              │       ─► if motion: start MP4 recording             │      │ camera_rules, users, ... │
              │       ─► every 5th frame: YOLOv8n person detection │      └──────────────────────────┘
              │       ─► per person: face detect + recognize        │      ┌──────────────────────────┐
              │       ─► activity rules (zones, loitering, …)       │ ───► │ Local files              │
              │       ─► raise_alert() ─► DB · WebSocket · email    │      │ recordings/ snapshots/   │
              └─────────────────────────────────────────────────────┘      │ faces/ (owner-only)      │
                 YOLO model + face models are loaded ONCE and shared       └──────────────────────────┘
```

**Design decisions that matter**

* **One thread per camera** — a bad RTSP URL or a crash in one camera's processing is caught inside that thread; the others keep running. FastAPI's event loop never does heavy work, so the web UI and live streams stay responsive.
* **Motion gates YOLO** — motion detection is cheap (milliseconds); YOLO runs only while a recording is already active and only every 5th frame. An idle scene costs almost nothing.
* **One shared YOLO / face model** behind a lock instead of one per camera: less memory, no concurrent GPU use.
* **Live view ≠ recording** — the live stream shows annotated copies (boxes, zones, names); recordings always contain the raw, unaltered video.
* **`raise_alert()` is the single door for alerts** — it stores the alert, publishes it to the WebSocket bus and hands it to notification channels (email today; adding another channel is a local change).
* **Secure by default** — nothing is reachable without a login, the server listens on `127.0.0.1`, and secrets come from environment variables.

---

## 🛠️ Technology stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12 | Best ecosystem for computer vision |
| Web API | **FastAPI** + Uvicorn | Fast, typed, async-capable (streaming, WebSocket), automatic validation |
| Computer vision | **OpenCV** | Capture, MOG2 motion, drawing, MP4 writing, YuNet/SFace face models |
| Person detection | **YOLOv8n** (Ultralytics, PyTorch, Apple-Silicon MPS) | Small, fast, accurate enough for people |
| Face recognition | **YuNet** (detector) + **SFace** (128-number embedding), run by OpenCV | No extra packages, ~39 MB, runs on CPU |
| Database | **SQLite** + SQLAlchemy 2.0 | Zero-setup, single file, plenty for a home system |
| Frontend | **React** + React Router + Vite + **Tailwind CSS** + lucide icons | Component-based dashboard, hot-reload dev server |
| Real-time | WebSocket (alerts), MJPEG (video) | Simple, works in every browser |
| Security | scrypt hashing, cookie sessions, CORS/Origin checks | Standard-library crypto, no extra dependencies |

---

## 📁 Project structure

```text
CCTV-Surveillance/
├── README.md                     ← this file
├── docs/
│   ├── PRESENTATION.md           slide-by-slide content for the college presentation
│   ├── VIVA.md                   likely viva questions with answers
│   └── DEMO.md                   the 4-minute live-demo script
├── deploy/
│   ├── Caddyfile.example         HTTPS reverse proxy for remote access
│   └── cctv.service.example      run the backend as a system service
├── backend/
│   ├── requirements.txt          pinned Python dependencies
│   ├── .env.example              every setting, documented (copy to .env)
│   ├── app/
│   │   ├── main.py               app creation, middleware, routers, startup/shutdown
│   │   ├── core/                 settings (config.py), clean-shutdown handling
│   │   ├── db/                   models.py (all tables), session.py (engine, light migration)
│   │   ├── api/                  one file per resource: auth, cameras, events, people,
│   │   │                         alerts, zones, rules, dashboard, sources, realtime, ...
│   │   ├── security/             passwords, sessions, throttle, middleware, bootstrap
│   │   └── services/
│   │       ├── camera/           sources (webcam/RTSP/HTTP/file), per-camera worker threads
│   │       ├── motion/           MOG2 motion detector
│   │       ├── detection/        shared YOLO person detector
│   │       ├── faces/            face detection/recognition, event tracker, private storage
│   │       ├── night/            lighting analysis + low-light enhancement
│   │       ├── activity/         zones, rules, loitering/repeated-entry/fall logic
│   │       ├── recording/        the motion→YOLO→faces→rules→recording pipeline, MP4 writer
│   │       ├── notifications/    email channel + dispatcher
│   │       ├── alerts.py         raise_alert() — the single entry point for alerts
│   │       └── alert_bus.py      pushes alerts to WebSocket clients
│   ├── scripts/
│   │   ├── make_demo_videos.py   creates demo "cameras" (day, street, night, infrared) + a demo face photo
│   │   └── manage_users.py       add / reset / disable accounts from the terminal
│   ├── tests/                    test_system.py (end-to-end), test_activity_rules.py,
│   │                             test_activity_pipeline.py, test_route_protection.py
│   ├── models/                   YOLO + face models (auto-downloaded, git-ignored)
│   ├── sample_videos/            demo videos (generated, git-ignored)
│   ├── data/                     cctv.db and .secret_key (created at runtime, git-ignored)
│   └── app/storage/              recordings/, snapshots/, faces/ (runtime, git-ignored)
└── frontend/
    ├── package.json · vite.config.js
    └── src/
        ├── pages/                Dashboard, Cameras, Events, Recordings, Alerts, People, Users, Login
        ├── components/           CameraTile, ZonesModal, AlertsPanel, VideoModal, ui/, layout/ ...
        ├── hooks/                auth, alerts (WebSocket), polling, cameras
        ├── utils/                formatting, alert/event/rule display metadata
        └── api.js                the one place that talks to the backend
```

---

## 🚀 Installation

### Requirements

| Needed | Version | Check |
|---|---|---|
| Python | 3.11 or 3.12 (3.12 tested) | `python3 --version` |
| Node.js | 18 or newer (v24 tested) | `node --version` |
| Internet | first start only | downloads YOLO weights (~6 MB) and the two face models (~39 MB) |
| Disk / RAM | ~3 GB for dependencies (PyTorch), 4 GB+ RAM | |

Developed and tested **only on an Apple-Silicon Mac** (YOLO uses the GPU through MPS). Windows/Linux
should work on the CPU, but untested — and OpenCV's pip build may lack the H.264 (`avc1`) video encoder there,
in which case recordings would not play in the browser.

### 1. Backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt       # takes a few minutes (PyTorch)
cp .env.example .env                  # then edit .env: set ADMIN_PASSWORD (at least 10 characters)
python scripts/make_demo_videos.py    # optional but recommended: demo cameras for testing / the demo
uvicorn app.main:app --port 8000
```

On the **first start** the server creates the database, the `admin` account (password from
`ADMIN_PASSWORD`; if you left it empty, a random one is printed once in the terminal), downloads the
models, and adds one "Local Webcam" camera. macOS asks for camera permission — click **Allow**
(start the server from a normal terminal window the first time so the dialog can appear).

> `ADMIN_PASSWORD` is only used when no users exist yet. To change a password later:
> `python scripts/manage_users.py set-password admin`.

### 2. Frontend (second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and sign in as `admin`.

### One-command alternative (serves the dashboard from the backend)

```bash
cd frontend && npm install && npm run build && cd ../backend
SECURITY__SERVE_FRONTEND=true uvicorn app.main:app --port 8000
```

Open **http://127.0.0.1:8000** — one program, one port, no Vite server.

### Verify the installation

```bash
cd backend && source venv/bin/activate
python -m tests.test_system           # ~2 minutes; starts a real server on a temporary database
```

---

## 📘 Usage guide

| Page | What you do there |
|---|---|
| **Dashboard** | Live camera grid (click ⤢ to enlarge), counters (online cameras, people now, events today, recordings, unread alerts, night cameras), active alerts, recent events. A **NIGHT MODE** badge appears on cameras in the dark. |
| **Cameras** | **Add camera**: choose the type — *Local webcam* (`0`), *RTSP/IP* (`rtsp://user:pass@192.168.1.50:554/stream1`), *HTTP/MJPEG*, or *Video file (loops)* from `backend/sample_videos/`. Use **Test connection** before saving. Edit, disable and delete cameras. The octagon **(!)** button opens **Zones & security rules**. |
| **Events** | Every detection, newest first. Filter by camera / type / status; play, download or delete the recording. Flagged events list *why* ("Person remained in restricted zone 'Driveway' for 32 seconds"). |
| **Recordings** | Thumbnail grid of saved clips with playback and download. |
| **Alerts** | All alerts with severity, snapshot, explanation and recording. Filter by state / type / severity / unread; **Mark read**, **Resolve**, **Mark all read**. Turn on browser notifications; email status and a test button. |
| **People** | Register family members: *Register person*, then *Add photos* (front-facing, clear, 3+ photos) or *Use camera*. The system tells you why a photo was rejected. |
| **Users** (admin) | Create viewer / admin accounts, disable or delete them, change roles. |

**Restricted zones and security rules** (Cameras → the octagon (!) button on a camera): click on the camera picture to
place the corners of a zone (3 or more), name it, choose a severity, optionally limit it to
certain hours, and set the loitering time and repeated-entry count. Below the list you can set the
camera's **security hours** (alert on any person) and switch on the experimental **fall-like** rule.

**Roles.** *admin* can change anything. *viewer* can watch cameras, events, recordings and alerts and
mark/resolve alerts, but cannot add cameras, delete anything or manage people and users.

**Testing without cameras.** Run `python scripts/make_demo_videos.py`, then add cameras of type
*Video file* pointing at `demo_entrance.mp4`, `demo_street.mp4`, `demo_night.mp4`,
`demo_infrared.mp4`. They loop forever, so they keep producing events. Delete them when finished.

---

## ⚙️ Configuration

Every setting can be set in `backend/.env` or as an environment variable; nested settings use a
double underscore (`FACE__KNOWN_THRESHOLD=0.45`). `backend/.env.example` documents all of them.

| Setting | Default | Meaning |
|---|---|---|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / random | First-start administrator |
| `MOTION__SENSITIVITY` | 30 | MOG2 threshold — higher = fewer false motion events |
| `MOTION__MIN_AREA` | 3000 | Smallest moving blob (pixels) that counts |
| `MOTION__POST_MOTION_SECONDS` / `MAX_RECORDING_SECONDS` | 5 / 30 | Keep recording after motion stops / cap per clip |
| `DETECTION__CONFIDENCE_THRESHOLD` | 0.5 | Minimum YOLO confidence for a person |
| `DETECTION__RUN_EVERY_N_FRAMES` | 5 | YOLO frequency while recording |
| `FACE__KNOWN_THRESHOLD` / `UNKNOWN_THRESHOLD` | 0.40 / 0.25 | Cosine-similarity cut-offs |
| `FACE__UNKNOWN_CONFIRMATIONS` | 3 | Separate sightings before an unknown-person alert |
| `NIGHT__ENTER_BRIGHTNESS` / `EXIT_BRIGHTNESS` | 55 / 75 | Night mode on/off brightness (with hysteresis) |
| `ACTIVITY__ZONE_EXIT_SECONDS` | 4 | Empty this long = the person left the zone |
| `ALERTS__CAMERA_OFFLINE_GRACE_SECONDS` | 20 | Offline this long before an alert |
| `EMAIL__ENABLED` + `EMAIL__HOST` … | off | Optional email alerts |
| `REMOTE_MODE`, `ALLOWED_HOSTS`, `CORS_ORIGINS`, `SECRET_KEY` | local | See [remote monitoring](#-security--remote-monitoring) |

Zone loitering / repeated-entry limits and per-camera security hours are stored in the database and
edited from the dashboard.

---

## 🔌 API documentation

Base URL `http://127.0.0.1:8000/api`. Interactive Swagger docs: **http://127.0.0.1:8000/docs**
(disabled in `REMOTE_MODE`). Authentication is a cookie set by `POST /auth/login`.
**User** = any signed-in account; **Admin** = administrators only; **Public** = no login.

| Method & path | Access | Purpose |
|---|---|---|
| `GET /health` | Public | liveness check |
| `POST /auth/login` · `POST /auth/logout` | Public | sign in (throttled) / sign out |
| `GET /auth/me` · `POST /auth/change-password` | User | current user / change own password |
| `GET /users` · `POST /users` · `PATCH /users/{id}` · `DELETE /users/{id}` | Admin | manage accounts |
| `GET /cameras` · `GET /cameras/{id}` | User | cameras with live status, people count, lighting (night/IR) |
| `POST /cameras` · `PATCH /cameras/{id}` · `DELETE /cameras/{id}` | Admin | add / edit / enable-disable / delete (history is kept) |
| `POST /cameras/test` | Admin | try a source without saving |
| `GET /cameras/{id}/stream` | User | live MJPEG stream |
| `GET /cameras/{id}/snapshot` | User | latest frame as a JPEG |
| `GET /events` | User | filters `camera_id`, `event_type`, `status`, `recordings_only`, `since`, `limit`, `offset`; each event includes `people` and `reasons` |
| `GET /events/{id}` · `/video` · `/download` · `/thumbnail` | User | details, playback (supports Range/seek), file download, preview image |
| `DELETE /events/{id}` | Admin | delete event and recording file |
| `GET /dashboard/summary` | User | all dashboard counters in one request |
| `GET /sources/files` | User | video files usable as a file camera |
| `GET /people` · `GET /people/{id}` · `GET /people/status` | User | registered people; recognition status |
| `POST /people` · `PATCH /people/{id}` · `DELETE /people/{id}` | Admin | register / rename / delete (removes face data) |
| `POST /people/{id}/faces` · `POST /people/{id}/faces/from-camera` · `DELETE /people/{id}/faces/{sample}` | Admin | add face photos (upload or from a camera) / remove one |
| `GET /alerts` | User | filters `state`, `type`, `severity`, `camera_id`, `unread`, `limit`, `offset` |
| `POST /alerts/{id}/read` · `/resolve` · `POST /alerts/read-all` | User | mark read / resolve |
| `GET /alerts/{id}/snapshot` · `DELETE /alerts/{id}` | User · Admin | snapshot image / delete |
| `GET /cameras/{id}/zones` · `POST /cameras/{id}/zones` | User · Admin | list / create a restricted zone |
| `PATCH /zones/{id}` · `DELETE /zones/{id}` | Admin | edit / delete a zone |
| `GET /cameras/{id}/rules` · `PUT /cameras/{id}/rules` | User · Admin | security hours and fall-detection switch |
| `GET /notifications/status` · `POST /notifications/test-email` | User · Admin | email channel status / send a test |
| `WS /ws/alerts` | User | real-time alert push (needs the session cookie) |

Errors use standard HTTP codes with a JSON `{"detail": ...}` body: `401` not signed in, `403`
not allowed / cross-site request, `404` not found, `409` duplicate name, `422` invalid input,
`429` too many login attempts.

**Alert object** (example)

```json
{
  "id": 12, "type": "suspicious_activity", "severity": "high",
  "camera_id": "street-view-38c7", "event_id": 41, "event_available": true,
  "message": "Person remained in restricted zone 'Driveway' for 32 seconds (limit 30 seconds)",
  "details": {"rule": "loitering", "zone": "Driveway", "dwell_seconds": 32,
              "threshold_seconds": 30, "confidence": 0.92,
              "confidence_note": "person detector confidence"},
  "created_at": "2026-10-04T12:33:15Z", "read": false, "resolved": false, "has_snapshot": true
}
```

---

## 🗄️ Database schema

SQLite file `backend/data/cctv.db` (created automatically; owner-only permissions). Tables are
defined in `backend/app/db/models.py`; new columns are added to existing databases automatically at startup.

```text
 cameras ─────────< zones                 (camera_id)
    │  └──────────< camera_rules          (camera_id, one row per camera)
    │
    └ (id, kept even if the camera is deleted)
 events ──────────< person_detections     (event_id)      one row per "new person seen"
    │  ├──────────< face_observations     (event_id)  >──── people ────< face_samples
    │  └──────────< alerts                (event_id, optional)
 users ───────────< user_sessions         (user_id)
```

| Table | Key columns | Purpose |
|---|---|---|
| `cameras` | `id` PK, `name`, `type` (webcam/rtsp/http/file), `source`, `enabled`, `created_at` | Configured sources. Live status is runtime state, not stored. |
| `events` | `id` PK, `camera_id`*, `event_type` (motion / person / suspicious_activity / unknown_person / restricted_area), `timestamp`*, `ended_at`, `recording_path`, `status` (recording / completed / interrupted / failed), `max_confidence` | One row per recording. The type is the most serious thing seen during it. |
| `person_detections` | `event_id`*, `camera_id`*, `confidence`, `bbox_x1..y2`, `timestamp`* | YOLO sightings |
| `people` | `id` PK, `name`, `created_at` | Registered people |
| `face_samples` | `person_id`*, `embedding` (128 floats, BLOB), `image_path`, `detection_score`, `face_px` | A registered face — the number vector, plus a 200 px thumbnail (the uploaded photo is not kept) |
| `face_observations` | `event_id`*, `camera_id`*, `person_id`*, `label` (known/unknown/uncertain), `similarity`, `detection_score`, `snapshot_path`, `timestamp`* | Every recognized face |
| `alerts` | `id` PK, `type`*, `severity`*, `camera_id`*, `event_id`, `message`, `details` (JSON), `snapshot_path`, `dedupe_key`*, `occurrences`, `created_at`*, `acknowledged_at` (read), `resolved_at`, `resolved_by` | Unknown person, restricted area, suspicious activity, camera offline |
| `zones` | `camera_id`*, `name`, `points` (JSON polygon, 0–1 coordinates), `enabled`, `schedule_start/end`, `severity`, `loiter_seconds`, `repeat_entries`, `repeat_window_seconds` | Restricted areas |
| `camera_rules` | `camera_id` PK, `quiet_start`, `quiet_end`, `fall_detection` | Security hours and the fall switch |
| `users` | `username`*, `password_hash` (scrypt), `role` (admin/viewer), `disabled`, `last_login_at` | Accounts |
| `user_sessions` | `token_hash`*, `user_id`*, `created_at`, `last_seen_at`, `expires_at`, `ip`, `user_agent` | Login sessions (only a keyed hash of the token is stored) |

`*` = indexed. `events.camera_id` deliberately has no foreign key so deleting a camera keeps its history.
Files on disk: `app/storage/recordings/<camera>/<date>/*.mp4`, `snapshots/…/*.jpg`, `faces/…/*.jpg`.

---

## 🧠 How the AI works

```text
frame ─► lighting (day / low light / infrared)
      ─► MOTION (MOG2) ──no──► live view only
             │yes
             ▼
      start recording (raw frames) ─► every 5th frame:
      YOLOv8n "person" ──none──► (recording ends 5 s after motion stops)
             │persons
             ├─► face detect (YuNet) ─► embedding (SFace) ─► compare with registered people
             │        known · unknown (needs 3 confirmations) · not sure      ─► unknown → ALERT
             └─► activity rules: zone intrusion · loitering · repeated entry ·
                 security hours · fall-like                                   ─► ALERT
```

* **Motion (OpenCV MOG2).** Each pixel is modelled as a mixture of Gaussians that adapts over time, so
  slow changes (sunlight, exposure) fade into the background. Shadows are marked and ignored, a
  morphological open/dilate removes speckle, and only blobs larger than `min_area` count. A 30-frame
  warm-up avoids false triggers at start-up; a sudden average-brightness jump (lights switched) resets the model instead of firing an event.
* **Person detection (YOLOv8n).** One neural-network pass finds all objects; only COCO class
  *person* is kept, at 320 px input and ≥ 0.5 confidence. It runs only while a recording is active, every 5th frame.
* **Faces.** YuNet finds faces inside each person box; SFace turns a face into 128 numbers; cosine
  similarity to each registered person decides: ≥ 0.40 known, < 0.25 unknown, otherwise *not sure*.
  Small, dark or turned faces are never called "unknown", and an alert needs 3 separate confirmations.
* **Suspicious activity.** Not a "behaviour AI": a handful of explicit rules on the YOLO boxes.
  *Zone intrusion*: the person's feet (bottom-centre of the box) are inside a polygon for 2 cycles.
  *Loitering*: a visit inside a zone lasts longer than the zone's limit. *Repeated entry*: N separate
  entries within a period. *Security hours*: any person during the configured hours. *Fall-like*
  (experimental): box goes from upright to lying within 3 s and stays down 4 s. Every alert carries
  the rule, the numbers behind it and the person-detector confidence.
* **Night.** Average brightness (and colour spread, to spot monochrome infrared) are smoothed and
  compared with two thresholds. At night, motion is denoised and YOLO runs on both the raw and a
  contrast-enhanced copy (the better result wins). **Enhancement cannot create information that
  darkness removed**; it only re-maps detail the camera captured, and it amplifies noise.

| Tuning knob | Effect |
|---|---|
| Too many false motion events | raise `MOTION__SENSITIVITY` or `MOTION__MIN_AREA` |
| Strangers called "known" | raise `FACE__KNOWN_THRESHOLD` |
| Too many "not sure" | lower `FACE__KNOWN_THRESHOLD` slightly |
| Night people missed | expected in very dark footage — see limitations |

---

## 🔐 Security & remote monitoring

**Default: local only.** The server listens on `127.0.0.1`; every API route, live stream, snapshot,
recording and the alert WebSocket requires a login. `python -m tests.test_route_protection` walks every
route and fails if one is added without authentication.

**What protects it:** scrypt-hashed passwords · random session tokens stored only as keyed hashes ·
`HttpOnly` + `SameSite=Strict` cookies (`Secure` over HTTPS) · login throttling (5 failures lock that user+address for 5 minutes) ·
admin / viewer roles enforced on the server · Host-header allow-list · Origin check on writes and WebSockets (CSRF) ·
explicit CORS origins (never `*`) · security headers · secrets only from environment variables · RTSP passwords hidden from non-admins · private file permissions on the database and face data.

**Reaching it from outside — in this order of preference**

1. **Private network (recommended):** install Tailscale or WireGuard on the server and on your phone/laptop; keep uvicorn on `127.0.0.1` and open it through the VPN. Nothing is public.
2. **Reverse proxy with HTTPS** ([deploy/Caddyfile.example](deploy/Caddyfile.example)): Caddy terminates TLS in front of uvicorn.
   Set in `backend/.env`: `REMOTE_MODE=true`, `ALLOWED_HOSTS`, `CORS_ORIGINS` (https), `PUBLIC_URL`, a 32+ character `SECRET_KEY`, a strong `ADMIN_PASSWORD`; build the frontend and set `SECURITY__SERVE_FRONTEND=true`. In remote mode the server **refuses to start** if any of this is unsafe.
3. **Never** port-forward 8000 straight from your router or bind `0.0.0.0` without a proxy.

A service-file example is in [deploy/cctv.service.example](deploy/cctv.service.example). Face data and recordings are sensitive: there is no per-camera permission model, and face embeddings are not encrypted at rest.

---

## ✅ Testing & results

**Test suites** (run from `backend/` with the virtualenv active)

| Command | What it proves | Time |
|---|---|---|
| `python -m tests.test_system` | **End to end**: starts the real server on a temporary database, adds 4 video cameras + 1 broken camera, and checks authentication, roles, multi-camera streaming, motion → YOLO → recording → playback, event history, night/IR detection, face registration and recognition, unknown-person alerts, every suspicious-activity rule, the alert lifecycle, WebSocket delivery, camera-offline alerts, dashboard counters, error handling, clean shutdown, database integrity and restart recovery | ~2 min |
| `python -m tests.test_activity_rules` | Every suspicious-activity rule in isolation, with positive **and** negative cases (flicker, sitting vs lying, slow lowering, idle gaps, cooldowns, schedules) and a controlled clock | seconds |
| `python -m tests.test_activity_pipeline` | The rules through the real motion → recording → detection pipeline, linked to recordings | seconds |
| `python -m tests.test_route_protection` | Every HTTP/WebSocket route requires login; writes require admin | seconds |
| `cd ../frontend && npm run lint && npm run build` | Frontend has no lint errors and builds | seconds |

**Results** (clean install on a fresh virtualenv, Apple-Silicon Mac, Python 3.12, Node 24)

| Suite | Result |
|---|---|
| `tests.test_system` (end to end, real server) | **116 / 116 checks passed** (77–102 s) — authentication 15, roles 7, cameras & error handling 21, detection / recording / events 13, night 5, faces 10, suspicious-activity rules 16, alerts & WebSocket 14, dashboard 3, database / shutdown / restart 12 |
| `tests.test_activity_rules` | **16 / 16 passed**; three rules were deliberately broken to confirm the tests fail when they should |
| `tests.test_activity_pipeline` | **3 / 3 passed** |
| `tests.test_route_protection` | **3 / 3 passed** (49 method/route combinations inspected) |
| Frontend `npm run lint` · `npm run build` | no warnings · builds (≈375 kB JS, 112 kB gzipped) |
| Clean install | new virtualenv from `requirements.txt` + `npm ci` → all of the above pass |

The end-to-end test found and fixed a real defect during final verification: RTSP camera URLs
(including passwords) were returned to viewer accounts by the API; viewers now only receive the masked address.

**Measured behaviour** (from development tests, not benchmarks on your cameras)

* Night person recall, moderate / dark / very dark frames: 97 % / 83 % / 56 % with the raw+enhanced strategy, versus 97 % / 82 % / 21 % raw only.
* Face model: the same person scored 0.64–0.96 cosine similarity against their registration; a different person 0.02–0.27.
* No false motion events from abrupt lighting changes in either direction; real motion still detected.
* Verified safe failure: face-model crash, SMTP outage, unreachable camera and killed server (recording recovered as *interrupted*) never stopped the other cameras.

---

## ⚠️ Known limitations

* **Not a certified security product.** Do not rely on it alone for safety-critical decisions.
* **Face recognition is statistical.** Lighting, angle, distance and camera quality matter; it can miss a registered person and, rarely, match a stranger. Small, dark or turned faces are reported *not sure* instead of guessed. Thresholds should be tuned on your own cameras.
* **Night detection is weaker.** Enhancement cannot recover information darkness removed; in very dark footage only about half of the people are found. Night faces are less reliable.
* **Suspicious activity = explicit rules, not understanding of intent.** "Feet inside the zone" assumes a camera that sees the floor from a normal angle. The fall-like rule judges only a rectangle (no pose), so it can miss falls (hidden, overhead view) and fire when someone lies down quickly; a person first seen already lying never triggers it. It is experimental and off by default.
* **Detection only runs while there is motion.** Someone standing perfectly still for a long time may stop being analysed.
* **YOLOv8n is the smallest model** — chosen for speed; it can miss small or partly hidden people.
* **Streaming is MJPEG** — simple and universal, but heavy on bandwidth and with no audio. Over the internet use a VPN or reduce cameras. More than 4 cameras fall back to refreshing snapshots (browser connection limit).
* **Single machine, SQLite.** Fine for a home (a handful of cameras); not for dozens of cameras or multiple servers. No automatic deletion of old recordings yet — watch disk space.
* **No audio, PTZ control, mobile app or push notifications** (email and browser notifications only; the page must be open for the latter).
* **Tested on macOS (Apple Silicon) only.**
* **Local data is not encrypted at rest**; protect the computer itself.
* The security-hours and zone schedules use the *server's* local time.

---

## 🔮 Future improvements

* Automatic retention policy (delete or archive recordings older than N days) and a disk-usage meter.
* Pose estimation (e.g. YOLOv8-pose) for a more reliable fall detection and "hands near door" style rules.
* Push notifications (Telegram / mobile push) and SMS.
* WebRTC or HLS streaming for lower bandwidth and audio.
* Larger or fine-tuned detection models, a GPU server for many cameras, and tracking across cameras.
* Better night handling: dedicated low-light models or IR-aware calibration per camera.
* Face-data encryption at rest, per-camera permissions, two-factor login.
* Analytics dashboard (activity heatmaps, busiest hours) and exportable reports.
* Docker packaging for one-command deployment.

---

## 🧰 Troubleshooting

| Problem | Fix |
|---|---|
| Can't log in / forgot the password | `cd backend && python scripts/manage_users.py set-password admin` |
| Server prints a random admin password I missed | Same command, or delete `backend/data/cctv.db` (this erases all data) and restart with `ADMIN_PASSWORD` set |
| Webcam shows *Offline* on macOS | System Settings → Privacy & Security → Camera → allow your terminal; only one program can use the webcam at a time |
| `Address already in use` | Another server uses port 8000: `lsof -i :8000`, stop it, or use `--port 8001` (and change the proxy target in `frontend/vite.config.js`) |
| First start is slow / models won't download | Needs internet once. Face recognition turns itself off if its models can't download; everything else keeps working |
| Blank dashboard / "Not authenticated" loop | Make sure the backend is running on port 8000 and open the address Vite prints (`http://localhost:5173`) |
| Recordings won't play | They are H.264 MP4; use a current Chrome / Safari / Edge |
| Too many events from the demo videos | They loop forever — disable or delete the demo cameras |
| Start over from scratch | Stop the server, delete `backend/data/` contents (except `.gitkeep`) and `backend/app/storage/` contents |

---

## 🎯 Vision

An AI-assisted home surveillance platform that moves beyond a wall of video feeds: it watches for you,
records only what matters, tells you *what* it saw and *why* it raised an alert — and keeps your video
and your face data in your own hands.
