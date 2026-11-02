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
7. [Checking alerts yourself](#-checking-alerts-yourself) · 7a. [Fire and smoke detection](#-fire-and-smoke-detection) · 7b. [Configuration](#-configuration) · 8. [API documentation](#-api-documentation) ·
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
| 🔔 **Alert system** | Types: unknown person, restricted area, suspicious activity, fire, smoke, camera offline. Severity (low → critical), timestamps, unread → read → resolved lifecycle, real-time delivery over WebSocket, toasts, browser notifications, optional email (off by default, pluggable) |
| 🕵️ **Suspicious-activity rules** | Restricted-zone intrusion, loitering in a zone, repeated entry, unusual (security) hours, and an experimental fall-like rule. Plain rules, each alert states *which* rule fired and *with what numbers* |
| 👥 **Crowd counting** | Counts distinct people in view (or inside one zone), shows the count on the camera tile and raises an alert when at least N people stay for a set time. Duplicate boxes round one person are merged. The count is an **"at least"** figure: a standard detector misses overlapping people, so it is never presented as exact |
| 🔥 **Fire and smoke detection** | A second small AI model (YOLOv8n trained on the D-Fire dataset) looks for flames and smoke about once a second on every camera, even in a still room. Fire and smoke are judged separately, need several detections in a few seconds, and raise one *critical* (fire) or *high* (smoke) alert with a snapshot and a short recording. It is an AI estimate with false alarms and misses: see [Fire and smoke detection](#-fire-and-smoke-detection) |
| 🧭 **Monitoring indicators** | Under every camera picture: which zones are watched (red while someone is inside), security hours, the crowd limit and progress, and whether the experimental fall check is on. When no rule is set it says so |
| 🌙 **Night surveillance** | Detects low light and infrared video automatically, shows **NIGHT MODE**, keeps person detection working (dual raw/enhanced pass). Recordings are never altered |
| 🌐 **Web app** | Public landing page and login page, then a protected, responsive dashboard (desktop, tablet, phone) with route guards and real-time data |
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
              │ CameraManager — per camera: a CAPTURE and an       │      ┌──────────────────────────┐
              │ ANALYSIS thread (capture never waits for the AI)    │      │ SQLite (cctv.db)         │
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

* **Isolated threads per camera** — a bad RTSP URL or a crash in one camera's processing is caught inside that camera's threads; the others keep running. FastAPI's event loop never does heavy work, so the web UI and live streams stay responsive.
* **The live picture never waits for the AI** — each camera has a light *capture* thread (read → draw boxes → JPEG, at the camera's own frame rate, never sleeping) and a separate *analysis* thread (motion, recording, YOLO, faces, rules) that always looks at the newest frame and skips the ones it was too busy for. A slow YOLO or face cycle delays the boxes by a few frames, never the video, and the camera driver's buffer can never fill up and put the picture seconds behind (see [Video smoothness](#video-smoothness)).
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
│   │       ├── detection/        shared YOLO person detector, shared fire/smoke detector
│   │       ├── faces/            face detection/recognition, event tracker, private storage
│   │       ├── night/            lighting analysis + low-light enhancement
│   │       ├── activity/         zones, rules, loitering/repeated-entry/fall logic, crowd counting, fire/smoke confirmation (fire.py)
│   │       ├── recording/        the motion→YOLO→faces→rules→recording pipeline, MP4 writer
│   │       ├── notifications/    email channel + dispatcher
│   │       ├── alerts.py         raise_alert() — the single entry point for alerts
│   │       └── alert_bus.py      pushes alerts to WebSocket clients
│   ├── scripts/
│   │   ├── make_demo_videos.py   creates demo "cameras" (day, street, night, infrared), six staged rule-test clips + a demo face photo
│   │   ├── night_benchmark.py    the same footage at falling brightness: classification, recall, false positives, timing
│   │   ├── crowd_benchmark.py    crowd-count accuracy on frames with a known number of people, at two detector sizes
│   │   ├── fire_check.py         try the fire/smoke model on a photo or video file (no server, no database)
│   │   ├── perf_benchmark.py     AI cost per stage, live-picture smoothness under load, alert latency
│   │   ├── soak_test.py          the real server left running with staged cameras: duplicates, delivery, CPU, memory, security checks
│   │   └── manage_users.py       add / reset / disable accounts from the terminal
│   ├── tests/                    test_system.py (end-to-end), test_activity_rules.py,
│   │                             test_activity_pipeline.py, test_route_protection.py, test_stream_latency.py,
│   │                             test_face_alerts.py, test_crowd.py, test_demo_clips.py, test_night.py,
│   │                             test_security_hardening.py
│   ├── models/                   YOLO + face models (auto-downloaded, git-ignored)
│   ├── sample_videos/            demo videos (generated, git-ignored)
│   ├── data/                     cctv.db and .secret_key (created at runtime, git-ignored)
│   └── app/storage/              recordings/, snapshots/, faces/ (runtime, git-ignored)
└── frontend/
    ├── package.json · vite.config.js
    └── src/
        ├── App.jsx               routes + guards (/ · /login · /dashboard · …)
        ├── pages/                Landing, Login, Dashboard, Cameras, Events, Recordings, Alerts, People, Users
        ├── components/           landing/ (navbar, hero, features, …), CameraTile, ZonesModal, AlertsPanel, ui/, layout/ ...
        ├── hooks/                auth, sign-out, alerts (WebSocket), polling, cameras
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

Open **http://localhost:5173** (the homepage), click **Login** or **Get Started**, and sign in as `admin`.

| Page | URL (dev server) | Access |
|---|---|---|
| Homepage (landing page) | http://localhost:5173/ | public |
| Login | http://localhost:5173/login | public (signed-in users are sent to the dashboard) |
| Dashboard | http://localhost:5173/dashboard | login required |
| Cameras · Alerts · Events · Recordings · People | `/cameras` · `/alerts` · `/events` · `/recordings` · `/people` | login required |
| Users | `/users` | administrators only |

Opening a protected page while signed out redirects to `/login` and brings you back to that page after signing in.
Every route also works after a browser refresh.

### One-command alternative (serves the dashboard from the backend)

```bash
cd frontend && npm install && npm run build && cd ../backend
SECURITY__SERVE_FRONTEND=true uvicorn app.main:app --port 8000
```

Open **http://127.0.0.1:8000** (homepage; `/login` and `/dashboard` work the same way) — one program, one port, no Vite server.

### Verify the installation

```bash
cd backend && source venv/bin/activate
python -m tests.test_system           # ~2 minutes; starts a real server on a temporary database
```

---

## 📘 Usage guide

| Page | What you do there |
|---|---|
| **Homepage** (`/`) | Public product page: what the system does, how the pipeline works, **Login** / **Get Started** buttons. Shows no camera data and makes no API calls except the session check. |
| **Login** (`/login`) | Username + password (show/hide), clear error messages. Wrong passwords are throttled by the server. **Sign out** (top right of the dashboard) ends the session on the server and returns to the homepage. Sessions last until you sign out or close the browser — there is deliberately no "remember me". |
| **Dashboard** (`/dashboard`) | Live camera grid (click ⤢ to enlarge), counters (online cameras, people now, events today, recordings today, unread alerts), a warning when a camera is offline, active alerts, recent events. A **NIGHT MODE** badge appears on cameras in the dark; the header shows backend and live-alert connection status, your name and role, and **Sign out**. All numbers come from the live API. |
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
*Video file* pointing at the clips. They loop forever, so they keep producing events. Delete them when finished.

| Clip | What it stages | With the zone on the **right half** of the picture, expect |
|---|---|---|
| `demo_empty.mp4` | an empty room with a little sensor noise | nothing at all |
| `demo_zone_entry.mp4` | one person walks in, steps into the zone, stands a few seconds, leaves | one *Restricted area* alert as they cross the middle (about 10 s in) |
| `demo_zone_loiter.mp4` | one person walks into the zone and stays about 25 s | the intrusion, then a *Loitering* alert after the zone's limit |
| `demo_crowd.mp4` | four people arrive one after another and stay together | a *Crowd* alert once at least 3 (your limit) have stayed for your duration; the tile shows 4 |
| `demo_repeated.mp4` | one person enters the zone and leaves, three times (visits at about 5, 27 and 49 s) | one intrusion, then *Repeated entry* on the third visit |
| `demo_lowlight_zone.mp4` | the zone-entry clip in a dim room (simulated, not real night) | the same single intrusion, with the **NIGHT MODE** badge |
| `demo_entrance.mp4`, `demo_street.mp4`, `demo_night.mp4`, `demo_infrared.mp4` | the original close-up and street scenes, a darkened one and a monochrome one | motion, person and face events; night / infrared badges |

The staged clips use cut-out people on a plain room, so they prove the rules work on real detector output for those scenes,
not on your real camera. The full walkthrough, including your MacBook webcam and phone, is in [docs/DEMO.md](docs/DEMO.md).

---

## 🔔 Checking alerts yourself

Alerts only appear when their condition is really met, so test each one on purpose. You need the backend
running, the camera added and enabled (**Cameras**), and at least one person registered (**People**: 3 clear,
frontal, well-lit photos, or use the camera).

| Alert | How to trigger it | What you should see |
|---|---|---|
| **Unknown person** | 1) Sit in front of the camera: your tile label should turn green with your **name**. 2) Have someone who is *not registered* face the camera for about 5 seconds, 1–2 m away, lit from the front and looking at it. | A red **UNKNOWN** label, then a toast and an entry on **Alerts** with a snapshot and an explanation ("judged unknown in 3 separate checks … best match 0.12"). Needs 3 sightings in one recording (5 at night); one alert per camera per 60 s |
| **Face not judged** (no alert, by design) | Turn your head sideways, cover the lens partly, or sit in a dark room | An orange **NOT SURE · reason** on the tile; **Events** shows *Face not judged: too dark to judge: brightness 31 (needs 40)* or *face turned away: yaw 0.62 (max 0.40)* |
| **Restricted area, loitering, repeated entry** | **Cameras** → the octagon **(!)** button → draw a zone over the floor area, set *loiter after* 10 s and *repeated entry* 2 within 5 min → Save. Walk into the zone, stay 10+ s, leave and enter again | `zone_intrusion`, then `loitering`, then `repeated_entry` alerts, each saying which rule fired. **Without a saved zone none of these can ever fire** |
| **After hours** | Same dialog, *security hours*: set a window that includes the current time → Save rules. Walk in front of the camera | A `suspicious_activity / after_hours` alert |
| **Camera offline** | Enable a camera whose source cannot open (for example an `rtsp://127.0.0.1:9/x` address), or unplug a USB webcam | Camera tile shows *Offline*; an alert after 20 s; it resolves itself when the camera returns |

**Webcam vs phone camera.** A phone used as a camera (Continuity Camera, Camo, DroidCam) shows up as an extra
*webcam* device: add it as type *Local webcam* with source `1` (or `2`). Use landscape, put it at eye level,
and keep your face within about 2.5 m (on a typical 720p camera a face is only 48 px wide at roughly 2.8 m, the minimum the system will judge). At start-up the server log prints
`Camera <id> delivers 1280x720 at 30 fps`: if the frame rate is low (about 15) the room is too dark.

**Look at the evidence yourself** (read-only, safe while the server runs):

```bash
sqlite3 -readonly backend/data/cctv.db "select label, round(similarity,2) sim, reason, timestamp from face_observations order by id desc limit 10;"
sqlite3 -readonly backend/data/cctv.db "select type, severity, camera_id, created_at from alerts order by id desc limit 10;"
```

An empty `alerts` table with *uncertain* observations means faces were never clear enough to judge; an
empty `alerts` table with zero zones means no zone rule is configured yet.

---

## 🔥 Fire and smoke detection

A second, small YOLO model checks every camera for **flames** and **smoke**. It is an *AI estimate from a camera picture*, not a fire alarm: it
can mistake a red lamp, a sunset, steam, fog or a screen showing flames for a fire, and it can miss real smoke. **It does not replace a smoke detector.**

**How it works.** Once per second (`FIRE__INTERVAL_SECONDS`) the analysis thread of each camera gives the newest frame to the model. This happens on the analysis thread
only, so the live picture never waits for it (measured below), and it does *not* depend on motion or on a recording: smoke drifts slowly and a fire can start in a
still room. Then plain rules decide (`services/activity/fire.py`):

| Rule | Default | Why |
|---|---|---|
| Fire and smoke are judged **separately** (own confidence, own counters, own cooldown, own alert type) | fire ≥ 0.50, smoke ≥ 0.60 | Smoke is the easier one to imagine (see "Measured" below) |
| An alert needs several detections inside a window; **one frame never alerts** | fire 3, smoke 5, within 8 s | A flickering lamp or one odd frame is not a fire |
| **One alert per episode.** The episode ends after 10 s without a detection | `FIRE__CLEAR_SECONDS` | A fire burning for minutes is one alert, not hundreds |
| **Cooldown** between alerts of the same kind on one camera | fire 120 s, smoke 180 s | A confirmation that falls inside the cooldown is held back and raised when the cooldown ends if it is still there, never silently lost |
| A camera outage ends the episode | always | Nothing is counted across a gap |

**What an alert stores** (the normal alert table, through `raise_alert()`): camera, time, type (`fire` / `smoke`), severity (critical / high), the model's confidence, how many
checks confirmed it, the boxes, a plain-English explanation, a **snapshot with the boxes drawn on it** (private, mode 600), and the recording. If nothing was moving, a clip is
started anyway as evidence, and it keeps recording while the fire or smoke is in view. The Alerts page shows it with its explanation, the dashboard tile shows a red **FIRE** / **SMOKE**
chip (amber *POSSIBLE FIRE 2/3* while it is still being confirmed) and an orange / grey box on the live picture, and the Events and Recordings pages can filter by Fire and Smoke. Email (if configured) includes both
(they are at or above the default `high` level).

### The model

| | |
|---|---|
| Model | `rabahdev/fire-smoke-yolov8n`, file `best.pt`, saved as `backend/models/fire_smoke_yolov8n.pt` |
| Source | https://huggingface.co/rabahdev/fire-smoke-yolov8n |
| What it is | YOLOv8n fine-tuned from the COCO `yolov8n.pt` on the **D-Fire** dataset (14,122 training images), 640 px input, 6.23 MB (SHA-256 `b9163379…4f28f`, the file all tests here used) |
| Classes | `0 = smoke`, `1 = fire` (the code reads the names from the model, never the numbers, and refuses a model that does not have both) |
| Published accuracy | On its own 4,306-image test split: mAP50 0.754, mAP50-95 0.430 (smoke 0.499, fire 0.362) as stated on the model card; **I did not reproduce these numbers** |
| Licence | **AGPL-3.0** per the model card (inherited from Ultralytics YOLOv8, the same licence as the person detector already used here). I did **not** verify the licence of the D-Fire dataset itself: check it before any redistribution or commercial use |
| Compatibility | Loads and runs with the installed Ultralytics 8.3.55 (checked); runs on the Apple GPU (MPS) or the CPU |

The weights file is git-ignored (like `yolov8n.pt`) and **nothing is downloaded automatically**. On a new machine:

```bash
cd backend
curl -L -o models/fire_smoke_yolov8n.pt https://huggingface.co/rabahdev/fire-smoke-yolov8n/resolve/main/best.pt
```

Without the file the feature switches itself off with one log line (`Fire and smoke detection is OFF: …`) and everything else works. To use another model, put it anywhere and set
`FIRE__MODEL_PATH`; it must name its classes `fire` and `smoke`. To turn the feature off: `FIRE__ENABLED=false`.

### Testing it with your laptop webcam and a phone

**Never start a real fire or smoke to test this.** Show the camera a picture or video of one instead.

1. **Try the model alone, no server needed.** Save a photo or a short video of a flame, a candle, a campfire or smoke to your computer (or screen-record one on the phone and AirDrop it), then:
   ```bash
   cd backend && source venv/bin/activate
   python scripts/fire_check.py ~/Downloads/fire_clip.mp4 --save marked.jpg
   ```
   It prints what the model saw each second, whether the app **would** have raised an alert, and writes the best frame with its boxes. It uses a throwaway database.
2. **Laptop webcam.** Start the backend and frontend (see Installation), sign in, **Cameras → Add**, type *Local webcam*, source `0` (or enable the one that exists). Play a fire or smoke video **full screen on your phone or a second screen**, hold it close to and facing the webcam so it fills a good part of the picture, in a lit room.
   * Within a few seconds the live tile should show an orange box *fire NN %* and an amber chip *POSSIBLE FIRE 1/3*. After 3 detections within 8 s the chip turns red **FIRE**, a toast appears, and **Alerts** gets a *Fire · Critical* entry with a snapshot and *Recording* (for smoke it needs 5 detections and the model must be at least 60 % sure).
   * If nothing is detected, that is information: screens are small, glossy and flicker, and cartoon-like flames or very hazy smoke may not look like the training photos. Try `fire_check.py` with `--fire-conf 0.3` to see whether the model reacts at all, and see the tuning notes below.
3. **Phone camera as a camera.** Add the phone as another *Local webcam* (Continuity Camera / Camo / DroidCam show up as an extra device, source `1` or `2`; see [Checking alerts yourself](#-checking-alerts-yourself)), or use the phone's own camera app to film a screen playing a fire video and run step 1 on that recording. Either way the phone only supplies pictures; the server does all the detecting.
4. **Check it stays quiet.** Point the camera at a normal room, a lamp, a window at sunset or a kettle's steam: there should be no alert. (This is also where this model is weakest: see below.)

### Measured

* **Cost** (this Apple M3, simulated 30 fps 720p camera, real model): one model pass takes **7.3 ms** (p95 7.9 ms), once per camera per second. An idle room with the check on measured 30.0 fps live, p95 picture age 8.1 ms and 39 % of a core, identical to the same room with it off. With face recognition running on the same camera the live picture was **29.9–30.0 fps with and without** it (3 runs each, alternated), p95 picture age 7.5–7.8 ms vs 7.6–7.7 ms, process CPU 88–90 % vs 88 % of a core. Counting the capture thread's own frames directly gave 29.7–30.1 fps with the check on.
* **False alarms on footage with no fire** (401 frames sampled from the project's 10 video clips and its demo photo): **0 detections on 9 clips** (empty rooms, people, a crowd, night, infrared, low light) and **15 "smoke" detections at 0.51–0.74 confidence on one clip** (`demo_entrance.mp4`, out-of-focus TV footage whose blurred grey background looks like smoke to the model). With the first draft thresholds (smoke 0.50, 5 of 8 s) that clip raised a false smoke alert; the defaults above (smoke 0.60) do not, and a regression test keeps it that way. **This is a real weakness of the model's smoke class**: expect false smoke alerts in scenes with large, soft, grey, out-of-focus areas.
* **Recall was NOT measured.** No fire or smoke footage was available here, so I cannot tell you how often a real fire is missed or at what confidence it is detected. The defaults (fire 0.50, smoke 0.60) are cautious starting points chosen to avoid the false alarm above, not calibrated values. If your test shows real flames detected at 0.35–0.5, lower `FIRE__FIRE_CONFIDENCE`; if you get false alarms, raise it or `FIRE__*_CONFIRM_HITS`.

### Known limitations

* **Not verified on real fire, real smoke or a real camera.** All alert-path tests use scripted model output; the real model was only checked on footage that contains no fire. The dashboard was checked in a browser with scripted detections.
* False alarms (lamps, sunsets, steam, fog, soft grey backgrounds, screens) and misses (thin, distant or very pale smoke, small flames, a fire out of view) are expected for a nano-sized model. It does not detect heat, gas or fires you cannot see.
* Night and infrared: no special handling (fire is bright, so it may work; smoke in the dark almost certainly will not be seen). Not tested.
* A fire that keeps burning after its cooldown does not raise a second alert (one per episode). A very small flame needs `FIRE__INTERVAL_SECONDS` and the confidence thresholds tuned on your camera.
* Every camera is checked, including video-file demo cameras; there is no per-camera on/off switch (a single global one, `FIRE__ENABLED`).

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
| `WEBCAM_WIDTH` / `WEBCAM_HEIGHT` / `WEBCAM_FPS` | 1280 / 720 / 30 | Mode requested from a local webcam (`0` = camera default). Many laptop cameras default to 1080p, which doubles the work; the log shows what the camera really delivers |
| `CAPTURE_FPS` | 20 | How often the AI looks at the newest frame (and the playback rate of video-file cameras). The live picture itself follows the camera's own frame rate |
| `DETECTION__CONFIDENCE_THRESHOLD` | 0.5 | Minimum YOLO confidence for a person |
| `DETECTION__RUN_EVERY_N_FRAMES` | 5 | YOLO frequency while recording |
| `DETECTION__CROWD_IMGSZ` | 640 | YOLO input size on a camera that has a crowd limit (normal cameras use `DETECTION__IMGSZ`, 320) |
| `FIRE__ENABLED` / `FIRE__MODEL_PATH` | true / `models/fire_smoke_yolov8n.pt` | Fire and smoke detection and its weights file (missing file = feature off, logged) |
| `FIRE__FIRE_CONFIDENCE` / `FIRE__SMOKE_CONFIDENCE` | 0.50 / 0.60 | Minimum model confidence per class (smoke is stricter: it false-fired at 0.5-0.74 on one test clip) |
| `FIRE__FIRE_CONFIRM_HITS` / `FIRE__SMOKE_CONFIRM_HITS` / `FIRE__CONFIRM_WINDOW_SECONDS` | 3 / 5 / 8 | Detections needed inside the window before an alert |
| `FIRE__FIRE_ALERT_COOLDOWN_SECONDS` / `FIRE__SMOKE_ALERT_COOLDOWN_SECONDS` / `FIRE__CLEAR_SECONDS` | 120 / 180 / 10 | Gap between alerts of one kind per camera; seconds without a detection that end an episode |
| `FIRE__INTERVAL_SECONDS` | 1.0 | Seconds between model passes per camera |
| `FACE__KNOWN_THRESHOLD` / `UNKNOWN_THRESHOLD` | 0.40 / 0.25 | Cosine-similarity cut-offs |
| `FACE__UNKNOWN_CONFIRMATIONS` | 3 | Separate sightings before an unknown-person alert |
| `NIGHT__ENTER_BRIGHTNESS` / `EXIT_BRIGHTNESS` | 55 / 75 | Night mode on/off brightness (with hysteresis) |
| `ACTIVITY__ZONE_EXIT_SECONDS` | 4 | Empty this long = the person left the zone |
| `ACTIVITY__ZONE_ALERT_COOLDOWN_SECONDS` | 120 | Minimum gap between zone-intrusion alerts for one zone (lower it, e.g. 20, to repeat a demo quickly) |
| `ACTIVITY__CROWD_GRACE_SECONDS` / `CROWD_ALERT_COOLDOWN_SECONDS` / `CROWD_SEVERITY` | 3 / 300 / medium | A dip below the crowd limit shorter than the grace does not restart its timer; one alert per crowded episode and at most one per cooldown |
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
| `GET /events` | User | filters `camera_id`, `event_type`, `status`, `recordings_only`, `since`, `limit`, `offset`; each event includes `people`, `reasons` (rule alerts) and `uncertain_reasons` (why faces were *not sure*) |
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
| `face_observations` | `event_id`*, `camera_id`*, `person_id`*, `label` (known/unknown/uncertain), `similarity`, `detection_score`, `snapshot_path`, `reason` (why a face was *not sure*, with the measured value and its limit), `timestamp`* | Every recognized face |
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

frame ─► (once a second, independent of motion) fire/smoke model ─► 3 fire / 5 smoke
         detections in 8 s ─► cooldown ─► ALERT + snapshot + clip
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

### Security and reliability audit

A final audit read the code and tested the running server (temporary databases and storage; no real camera, no real secrets printed).

| Area | How it was checked | Result |
|---|---|---|
| Authentication and sessions | Code review; system test (login, cookie flags, throttling, CSRF) | Sound: keyed-hash tokens, idle and absolute expiry, disabled accounts refused, logout revokes server-side |
| Route protection and roles | `test_route_protection` walks all 49 route/method combinations; the soak run tries 11 admin actions as a viewer | Every one needs login; every write needs admin (11 of 11 refused with 403) |
| WebSocket | Unauthenticated and cross-origin handshakes refused; an authorised listener during the soak | All 34 stored alerts arrived, median 2 ms after being stored |
| Secrets and passwords | `git ls-files` for env/keys/databases; pattern search for hard-coded credentials; file modes | Nothing secret is tracked; `.env`, the session key and the database are git-ignored; key and database are owner-only (`600`). **Your `backend/.env` was `644` (readable by other users): the server now warns at start-up; run `chmod 600 backend/.env`** |
| Camera credentials | A viewer reads every camera route; the server log is searched for a canary password | A viewer never receives the address; the admin's display copy is masked; the password appears in no log line |
| Logs and private data | A password typed into the username box is searched for in the log | **Found and fixed:** it used to be logged ("Failed login for …"); an unknown username is no longer logged |
| File uploads | Size and count limits; a 7000x7000-pixel PNG of a few KB | **Found and fixed:** only the file size was limited, so a tiny file could declare gigapixels and need gigabytes to decode; photos over 40 megapixels are now refused before decoding |
| Recording and snapshot access | Login required on every route; stored paths | Paths come from the database, never from a request. As defence in depth they can no longer resolve outside the storage folder (symlinks included) |
| Database writes and migration | A 10-minute soak with 7 cameras writing events and alerts; both new migrations run on a copy of the real database | No `database is locked`, no traceback; rows and integrity intact |
| Camera loss | Offline alert, automatic resolve, reconnect (network stream), timers across outages | Works; no timer runs across an outage |

Still true, and not hidden: the login throttle is in memory (a restart clears it); there are no per-camera permissions; face embeddings are not encrypted at rest; the local server uses plain HTTP (use the VPN or HTTPS options above for remote access);
no dependency vulnerability scan was run (`pip-audit` is not installed and nothing was installed for the audit).

---

## ✅ Testing & results

**Test suites** (run from `backend/` with the virtualenv active)

| Command | What it proves | Time |
|---|---|---|
| `python -m tests.test_system` | **End to end**: starts the real server on a temporary database, adds 4 video cameras + 1 broken camera, and checks authentication, roles, multi-camera streaming, motion → YOLO → recording → playback, event history, night/IR detection, face registration and recognition, unknown-person alerts, every suspicious-activity rule, the alert lifecycle, WebSocket delivery, camera-offline alerts, dashboard counters, error handling, clean shutdown, database integrity and restart recovery, and a network (HTTP-MJPEG) camera that connects, drops and reconnects by itself | ~2 min |
| `python -m tests.test_stream_latency` | The live picture stays ~current and at the camera's frame rate while a slow AI runs, with a camera that queues frames; detection and recording still work; an unplugged camera goes offline and recovers | ~40 s |
| `python -m tests.test_face_alerts` | The unknown-person path: 3 confirmations (5 at night), uncertain faces never alert, nobody registered, unknown beside a known person, cooldown, quality gates report measured values, alert and observation explain themselves, and the real pipeline turns an unknown face into a stored alert | seconds |
| `python -m tests.test_activity_rules` | Every suspicious-activity rule in isolation, with positive **and** negative cases (flicker, sitting vs lying, slow lowering, idle gaps, cooldowns, schedules) and a controlled clock | seconds |
| `python -m tests.test_activity_pipeline` | The rules through the real motion → recording → detection pipeline, linked to recordings | seconds |
| `python -m tests.test_crowd` | Crowd counting: duplicate boxes merged, count in a zone, "approximate" flag, the over-the-limit timer (flicker, dips, gaps), one alert per episode, cooldown, camera interruption, rule off, honest wording | seconds |
| `python -m tests.test_demo_clips` | The six **staged clips** through the real pipeline with real YOLO: empty room, entering a zone, staying (loitering), crowd (alert at 3, none at 5), leaving and re-entering, low light, and a second visit that starts inside the cooldown; positive and negative | ~50 s |
| `python -m tests.test_fire_smoke` | Fire and smoke: the confirmation rules (one frame never alerts, fire and smoke separate, window, one alert per episode, cooldown held back then released, camera loss), per-class confidence thresholds and classes found by name on a **mocked model**, the stored alert (camera, time, confidence, type, severity, snapshot, recording, event upgraded, Events-page reason) through the real pipeline, quiet when nothing is seen, a slow or failing model never delays or breaks the pipeline, and three negative checks with the **real model** on staged footage (incl. the blurry-background clip that gave a false smoke alert) | seconds |
| `python -m tests.test_security_hardening` | A password typed in the username box is not logged, gigapixel photos are refused before decoding, stored paths cannot leave the storage folder, a world-readable `.env` is warned about | seconds |
| `python -m tests.test_night` | Day / low-light / infrared classification, brightness and colour-spread maths, hysteresis, smoothing, the enhancer, and the measured benchmark (enhancement never hurts, helps in the dark, cannot recover near-black) | ~30 s |
| `python -m tests.test_route_protection` | Every HTTP/WebSocket route requires login; writes require admin | seconds |
| `cd ../frontend && npm run lint && npm run build` | Frontend has no lint errors and builds | seconds |

**Results** (clean install on a fresh virtualenv, Apple-Silicon Mac, Python 3.12, Node 24)

| Suite | Result |
|---|---|
| `tests.test_system` (end to end, real server) | **143 / 143 checks passed** (93–145 s) — authentication 16, roles 7, cameras & error handling 21, detection / recording / events 13, night 5, faces 12, suspicious-activity rules 16, alerts & WebSocket 14, dashboard 3, database / shutdown / restart 12, network camera 8, crowd, monitoring & fire status 13, private data in the server log 3 |
| `tests.test_face_alerts` | **10 / 10 passed** (4 of them failed before the explanation fix, which proves they test something) |
| `tests.test_stream_latency` | **3 / 3 passed** (repeated 4 times, no flakiness); fails on the old single-thread design with "only 8.9 fps from a 30 fps camera" |
| `tests.test_activity_rules` | **21 / 21 passed** (5 new: camera interruption, kept entry count, long tracking loss, real 120 s cooldown, second person joining); the interruption tests were shown to fail when `interrupt()` is disabled |
| `tests.test_crowd` | **17 / 17 passed** |
| `tests.test_fire_smoke` | **25 / 25 passed** (22 with mocked model output, 3 with the real model on staged footage, none on real fire); mutation-checked: removing the per-class threshold, the once-a-second throttle, the camera-loss reset, or the Events-page reason each makes tests fail; one real defect it found (an episode did not end if no empty cycles were fed in) is fixed |
| `tests.test_security_hardening` | **4 / 4 passed**; the login-log and upload tests were shown to fail on the original code |
| `tests.test_demo_clips` | **7 / 7 passed** on real YOLO output (incl. the cooldown blind-spot regression, shown to fail without its fix); with duplicate-merging disabled the crowd clip shows a count of 7 and fires a false "5 people" alert |
| `tests.test_night` | **6 / 6 passed** |
| `tests.test_activity_pipeline` | **3 / 3 passed** |
| `tests.test_route_protection` | **3 / 3 passed** (49 method/route combinations inspected) |
| Frontend `npm run lint` · `npm run build` | no warnings · builds (≈424 kB JS, 126 kB gzipped) |
| Clean install | new virtualenv from `requirements.txt` + `npm ci` → all of the above pass |

The end-to-end test found and fixed a real defect during final verification: RTSP camera URLs
(including passwords) were returned to viewer accounts by the API; viewers now only receive the masked address.

**Measured behaviour** (from development tests, not benchmarks on your cameras)

* Night detection: see [Night mode, measured](#night-mode-measured) (reproducible with `scripts/night_benchmark.py`; it replaces earlier ad-hoc figures).
* Face model: the same person scored 0.64–0.96 cosine similarity against their registration; a different person 0.02–0.27.
* No false motion events from abrupt lighting changes in either direction; real motion still detected.
* Verified safe failure: face-model crash, SMTP outage, unreachable camera and killed server (recording recovered as *interrupted*) never stopped the other cameras.

---

### Night mode, measured

`python scripts/night_benchmark.py` replays the **same footage** at falling brightness and reports what the app does
(about 20 s). `python -m tests.test_night` asserts the properties below so they cannot drift.
*Recall* is relative to what YOLO finds in the same frames at normal light (there are no hand-labelled boxes), and the
footage is a darkened copy plus sensor noise, **not a real night camera**.

| Exposure / noise | Reported as | Brightness | Recall raw | Recall enhanced | Recall combined (the app) | Frames with more people than at normal light (raw / enh / combined, of 60) | False positives in an empty dark room (of 40 frames) | YOLO ms | Enhance ms |
|---|---|---|---|---|---|---|---|---|---|
| 1.00x / σ0 | day | 56 | 100% | 100% | 100% | 0 / 0 / 0 | 0 | 11.4 | 2.6 |
| 0.50x / σ4 | low light | 28 | 100% | 100% | 100% | 1 / 0 / 1 | 0 | 11.2 | 2.4 |
| 0.25x / σ4 | low light | 14 | 100% | 100% | 100% | 4 / 0 / 4 | 0 | 11.3 | 2.7 |
| 0.12x / σ4 | low light | 7 | 100% | 100% | 100% | 6 / 4 / 6 | 0 | 11.4 | 2.5 |
| 0.06x / σ4 | low light | 4 | 85% | 92% | **97%** | 0 / 3 / 3 | 0 | 6.5 | 2.2 |
| 0.06x / σ8 | low light | 5 | 37% | 63% | **65%** | 0 / 0 / 0 | 0 | 6.2 | 2.2 |
| 0.04x / σ10 | low light | 5 | 0% | 0% | 0% | 0 / 0 / 0 | 0 | 5.3 | 2.1 |
| 0.03x / σ12 | low light | 6 | 0% | 0% | 0% | 0 / 0 / 0 | 0 | 5.1 | 2.1 |

A synthetic monochrome clip is classified **infrared** (brightness 89, colour spread 3.4) and people are found in 100 % of its frames.
That is a software check only: **no infrared camera has been tested.**

What the numbers say:

* **Classification** works as designed: *low light* below brightness 55 (and back to day only above 75, so it cannot flicker), *infrared* for a bright picture with almost no colour (spread under 8), smoothed over about 2.5 s so a shadow or flash does not flip the mode (`test_night`).
* **Enhancement (gamma + CLAHE) helps exactly where raw detection starts to fail** and is useless beyond it: +12 points at 6 % exposure, +28 points with heavy noise, nothing once the picture is near-black. Information that was never captured cannot be recovered.
* **It costs almost nothing:** about 2.5 ms per 640x480 frame next to about 10 ms for a YOLO pass, so the night strategy (two passes plus enhancement) roughly doubles a detection cycle, which runs only a few times a second on the analysis thread and never touches the live picture.
* **No people appear in an empty dark room**, with or without enhancement (0 of 40 frames at every level).
* **A found-more-people rule needed fixing.** The night strategy keeps whichever pass finds more people, but the detector sometimes draws two boxes round one person, and the enhanced pass did so more often. Overlapping duplicates are now merged before the passes are compared (and before any counting), which removed those cases. Some frames still show one more box than at normal light, in the raw pass too: darkening changes how the detector splits boxes. The crowd count therefore uses a median over the last five cycles so a single-cycle extra box cannot make a crowd.

### Crowd counting

* **Counting:** every detection cycle takes the people YOLO found, merges duplicate boxes (a box mostly inside a stronger one, or overlapping it almost entirely, is the same person), and counts those whose feet are in the whole picture or in the chosen zone. The number shown is the median of the last five cycles, written **"N+"** because it is a lower bound.
* **Detector input size:** the app normally runs YOLO at 320 px (fast, fine for one person near a webcam). A camera that has a crowd limit runs it at **640 px** (`DETECTION__CROWD_IMGSZ`), because at 320 people standing close together are lost. The cost was measured: a YOLO pass takes about 12.6 ms instead of 6.9 ms, a few times a second, on the analysis thread (plus a one-off warm-up of about 0.3 s).
* **Alert:** at least *N* people for *S* seconds (set per camera under **Cameras → (!) → Alert when at least N people stay for S seconds**). A dip shorter than 3 s does not restart the timer; one alert per crowded episode; at least 5 minutes between alerts. The alert says "At least N people…" and carries the count, both limits, and a note that the real number can be higher.
* **Accuracy, measured** with `python scripts/crowd_benchmark.py` on frames whose true count is known because the frames were built (people placed in a row, 8 frames per setting, real YOLOv8n). These are clean cut-outs on a plain room, so this is the **best case**:

| True people | Exactly right, no overlap: normal size → crowd size | Average count when neighbours overlap 25 % / 50 % / 75 % (crowd size) |
|---|---|---|
| 1 | 100 % → 100 % | 1.0 / 1.0 / 1.0 |
| 2 | 100 % → 100 % | 1.8 / 1.1 / 1.0 |
| 3 | 38 % → **100 %** | 2.5 / 1.9 / 1.0 |
| 4 | 25 % → **100 %** | 3.0 / 2.2 / 1.4 |
| 6 | 12 % → **100 %** | 4.9 / 3.2 / 1.8 |
| 8 | 0 % → **100 %** | 6.6 / 3.5 / 2.1 |

  People who are shoulder to shoulder are counted correctly; **as soon as they overlap, the count falls fast** (eight people overlapping by half average 3.5). The count never came out too high once duplicate boxes were merged (up to 12 % of frames did without the merge). A standard person detector cannot count a dense crowd.
* **Limits:** overlapping or hidden people are missed (see the table), very small or distant people are missed, and the count updates only while the camera sees movement. Do not use it as an exact head count or for safety limits.
* **Verified:** merging and the timer with scripted boxes (`test_crowd`, 17); on staged footage with the real detector, the four staged people never counted as more than four and a limit of five never fired, while with merging switched off the same clip showed a count of 7 and fired (`test_demo_clips`); live in the dashboard.

### What is verified, and how

| Status | Feature | Evidence |
|---|---|---|
| ✅ Works, verified with the real detector on staged footage | Person detection; motion-triggered recording; restricted-zone intrusion (one alert per entry, cooldown); loitering; repeated entry; crowd count and alert; low-light detection; empty scene stays silent; drawing a zone in the dashboard (stored fractions match where the server draws it, also on a 4:3 camera) | `test_demo_clips` (real YOLO, six staged clips), browser check |
| ✅ Works, verified with scripted detections and a fake clock | Security hours; timers across detection gaps, tracker loss and camera interruptions; cooldowns and de-duplication; negative cases for every rule | `test_activity_rules` (21), `test_crowd` (17), `test_face_alerts` (10), `test_security_hardening` (4) |
| ✅ Works, verified end to end on a real server | Alerts to database, WebSocket and dashboard; camera offline and reconnect (a network stream stands in for RTSP); crowd alert from a camera; monitoring status; rule validation; a 20-minute soak with seven cameras (no duplicate, no false alert, no error, no database lock) | `test_system` (143), `scripts/soak_test.py` (15 checks) |
| ⚠️ Implemented; alert path verified with mocked model output, real model checked only for false alarms | Fire and smoke detection: confirmation rules, thresholds, cooldowns, stored alert with snapshot and clip, dashboard display (scripted detections in a browser), no effect on the live picture. **Not tested on real fire or smoke, recall unknown**, and one false-alarm source found (soft grey backgrounds) | `test_fire_smoke`, `scripts/fire_check.py`, [Fire and smoke detection](#-fire-and-smoke-detection) |
| ⚠️ Implemented, verified only on simulated or photo footage | Face recognition and unknown-person alerts (photo-based demo, not your cameras); night mode (darkened clips); infrared (a synthetic monochrome clip, **no infrared hardware**); webcam and RTSP capture (simulated cameras) | needs real-world validation with your webcam and phone: see [docs/DEMO.md](docs/DEMO.md) |
| 🧪 Experimental | Fall-like detection (box shape only, **off by default**, only scripted boxes tested); lingering-in-view rule (off by default) | not reliable; needs human review |
| ❌ Not built | Pose-based fall detection (needs a pose model download); persistent-identity multi-person tracking; dense-crowd density estimation | listed under [future improvements](#-future-improvements) |

### Performance, measured

**Conditions.** Apple M3 (8 cores, 8 GB RAM), macOS, real YOLOv8n and face models. **No real camera:** a simulated 30 fps 720p webcam (staged clips), so these numbers describe the software, not your camera.
Reproduce with `python scripts/perf_benchmark.py` (about 5 minutes) and `python scripts/soak_test.py` (see below). "Picture age" is the true time between a frame being captured and it being published as the live JPEG.
CPU is the whole benchmark process, **including the test harness itself** (generating frames and decoding JPEGs to read their stamps, about half a core), so the app's own cost is the difference from the baseline row.
The fire/smoke check's own numbers (a 7.3 ms pass once a second; no change in live fps, picture age or CPU in A/B runs) are in [Fire and smoke detection](#-fire-and-smoke-detection).

**Live picture while the AI works** (20 s measured after an 8 s warm-up):

| Load | Live fps | Picture age median / p95 / max (ms) | AI cycle median / p95 / max (ms) | CPU (% of one core) |
|---|---|---|---|---|
| Baseline: capture + motion + recording, no AI models | 28.9 | 5.5 / 8.4 / 34.0 | 13.4 / 14.8 / 19.4 | 50 |
| YOLO only, 4 staged people | 29.0 | 5.6 / 8.5 / 32.8 | 13.4 / 27.3 / 59.5 | 52 |
| + zone + crowd rule (YOLO at 640 px) | 28.8 | 6.4 / 9.5 / 40.7 | 12.8 / 34.4 / 58.4 | 55 |
| YOLO only, close-up faces | 29.6 | 5.1 / 7.8 / 32.2 | 21.3 / 34.0 / 81.9 | 82 |
| + face recognition | 30.0 | 5.1 / 7.6 / 27.8 | 21.2 / 69.4 / 92.2 | 87 |
| + faces + zone + crowd rule | 30.0 | 5.2 / 8.3 / 33.1 | 21.2 / 65.0 / 85.3 | 88 |
| Dim clip: night mode (raw and enhanced YOLO passes) | 30.0 | 5.5 / 8.3 / 32.1 | 9.7 / 40.2 / 285.9 | 93 |

* **Slow AI never blocks the camera:** the live picture stays at 29–30 fps with a p95 age under 10 ms in every load, while one AI cycle can take up to 0.29 s. (A first run of the same benchmark saw one single frame stall to 103 ms in the heaviest load; it did not recur, so it is an occasional event, not a constant one.)
* **What each feature costs** (same footage, feature off and on): crowd counting +3 CPU points and +7 ms at the p95 of an AI cycle; face recognition +5 CPU points and +35 ms at the p95 of an AI cycle (it adds work only on cycles that contain a face); the night strategy doubles the YOLO calls (7.2 per second against 3.5) and adds about 6.7 ms of enhancement per pass. None of it touches the live picture.
* **Cost per call:** YOLO pass 10.9–11.6 ms at 1280x720, face detect + recognise about 23 ms (p95 38 ms), night enhancement 6.7 ms, duplicate merge + crowd count 0.016 ms.

**Alert latency.** Each staged clip is played in real time. The footage defines the earliest moment each alert could legitimately fire (the detector run on every frame); the delay after that was:
zone intrusion **0.9–1.2 s**, loitering **0.7 s**, crowd **0.6 s**. That includes waiting for two confirming detection cycles, the median over five cycles, and a recording starting. Delivery from the database to a WebSocket client added a median of 2 ms (max 21 ms).

**Soak test** (`python scripts/soak_test.py --seconds 1200`): the real server on a temporary database with six staged cameras and one unreachable RTSP camera, left running for 20 minutes:
**160 alerts, 0 duplicates** (nothing closer together than its cooldown, which was shortened for the run), **0 alerts from the empty room**, every scenario produced its alert, every alert had a snapshot and an event with a recording and a timestamp inside the run,
all 160 reached a connected WebSocket client, a viewer was refused 11 of 11 administrative actions, no camera password or admin password reached the log, and **no error, traceback or database lock** appeared in the log.
Server process: median **127 %** of one core (peak 175 %, on an 8-core machine) and about **730–1,010 MB** of memory (per-minute medians; the single highest sample was 1,109 MB) with no sustained climb over the 20 minutes (the first ten minutes averaged 873 MB, the last ten 867 MB).
This rules out an obvious leak over 20 minutes; it cannot prove days of uptime, so run `--seconds 3600` overnight if that matters to you.
One earlier 10-minute run reported 2 of 80 alerts not seen by the WebSocket client; the check was then changed to count only alerts raised after the client connected (a WebSocket is a live feed), and the following 20-minute run lost none. I could not prove the earlier two were raised before the connection, so treat WebSocket delivery as measured but not formally proven; the dashboard also polls every 15 s, so an alert is never missing from the page.

### Video smoothness

Live video used to lag, so it was measured and fixed. The test camera delivers 30 fps on its own clock
with real person footage while the real YOLO and face models run (the real webcam was not available to
the test environment, so this is a simulation, not a benchmark of your hardware). "Picture age" is the time between
a frame being captured and it being published as the live JPEG.

| Case (30 fps source, person walking, recording + YOLO + faces active) | Before | After |
|---|---|---|
| 720p, driver keeps only the newest frame | 17.6 fps · picture age p95 100 ms, max 223 ms | **30 fps · p95 8 ms, max 10 ms** |
| 720p, driver queues frames (RTSP / FFmpeg style) | 17.5 fps · **1,345 ms old** | **30 fps · p95 8 ms, max 20 ms** |
| 1080p, newest-frame driver | 16.0 fps · p95 128 ms, max 476 ms | **30 fps · p95 11 ms, max 51 ms** |

Detection kept pace: YOLO ran 117 times before and 118 after over the same 720p footage (106 and 110 at 1080p), with people found and
recordings made. At 1080p the AI side runs about 17 cycles a second instead of 20 because each frame is heavier, which is why the webcam is asked for 720p by default. `python -m tests.test_stream_latency` keeps this from regressing (it fails on the old design
with "only 8.9 fps from a 30 fps camera").

---

## ⚠️ Known limitations

* **Not a certified security product.** Do not rely on it alone for safety-critical decisions.
* **Face recognition is statistical.** Lighting, angle, distance and camera quality matter; it can miss a registered person and, rarely, match a stranger. Small, dark or turned faces are reported *not sure* instead of guessed. Thresholds should be tuned on your own cameras.
* **Night detection is weaker.** Enhancement cannot recover information darkness removed: on the benchmark clip people are still found in 97 % of frames at 6 % exposure, but only 65 % at 6 % exposure with heavy noise and 0 % below that (see [Night mode, measured](#night-mode-measured)). Night faces are less reliable. Infrared hardware has **not** been tested; the infrared row is a synthetic monochrome clip.
* **A crowd count is a lower bound.** A standard person detector (YOLOv8n) finds people one by one. People who overlap, stand behind each other, are small or partly hidden are missed or merged, so dense crowds are under-counted, and the app says "at least N". It cannot count a packed crowd; that needs a density-estimation model.
* **Zones track occupancy, not individuals.** A zone is "occupied" or not. If a second person walks into an already occupied zone it is not a new entry, and people are not given persistent identities (nearest-box matching only, enough for dwell time). A tracking outage longer than the exit gap, or a camera interruption, ends a visit and the next sighting starts a new one (its time is never carried across the gap).
* **Fall detection is not reliable and is off by default.** It looks only at the shape of a person's box. It was verified with scripted boxes, not with real falls, and it must not be used as a safety device; every alert asks for a human to review the recording. A pose-based version is **not built** (it needs a pose model download, about 6 MB).
* **Suspicious activity = explicit rules, not understanding of intent.** "Feet inside the zone" assumes a camera that sees the floor from a normal angle. The fall-like rule judges only a rectangle (no pose), so it can miss falls (hidden, overhead view) and fire when someone lies down quickly; a person first seen already lying never triggers it. It is experimental and off by default.
* **Analysis starts on motion.** A person who walks in is watched for as long as the detector keeps seeing them (a new person who arrives while the 10 s cooldown after a recording is running is found too: this was a bug, fixed). But someone who is already standing still when the system starts, or whom the motion model has absorbed into the background, is not analysed until something moves.
* **Fire and smoke detection is an AI estimate and was not tested on real fire.** See [Fire and smoke detection](#-fire-and-smoke-detection): false alarms (steam, fog, soft grey backgrounds, lamps, screens) and misses are expected, recall was not measured, and it is not a substitute for a smoke detector.
* **Everything with a camera was tested in simulation.** No real webcam, phone camera or infrared camera was available to the tests; the staged clips are cut-out people on a plain room.
* **YOLOv8n is the smallest model** — chosen for speed; it can miss small or partly hidden people.
* **Streaming is MJPEG** — simple and universal, but heavy on bandwidth and with no audio. Over the internet use a VPN or reduce cameras. More than 4 cameras fall back to refreshing snapshots (browser connection limit).
* **Single machine, SQLite.** Fine for a home (a handful of cameras); not for dozens of cameras or multiple servers. No automatic deletion of old recordings yet — watch disk space.
* **No audio, PTZ control, mobile app or push notifications** (email and browser notifications only; the page must be open for the latter).
* **Tested on macOS (Apple Silicon) only, with the built-in Chromium-based browser.** Not tested: Safari and Firefox (the code uses Safari's `-webkit-` fallbacks, and Tailwind v4's own minimums apply: Safari 16.4+, Chrome 111+, Firefox 128+); a real webcam or RTSP/IP camera (the webcam path was only measured with a simulated camera, and a local HTTP-MJPEG stream stands in for RTSP in the tests). Tablet widths (768 and 1024 px) were checked in the browser, desktop and phone widths earlier.
* **The landing-page preview is an illustration.** Its cameras, figures and alerts are sample data and are labelled so; the dashboard behind the login shows only real data.
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
| Start-up warning: `.env can be read by other users` | Run `chmod 600 backend/.env`. The file holds the admin password and the secret key |
| Can't log in / forgot the password | `cd backend && python scripts/manage_users.py set-password admin` |
| Server prints a random admin password I missed | Same command, or delete `backend/data/cctv.db` (this erases all data) and restart with `ADMIN_PASSWORD` set |
| Events appear but no *unknown person* alert | See [Checking alerts yourself](#-checking-alerts-yourself). Short version: an unknown-person alert needs a face the system can judge (**at least 48 px wide, brightness at least 40, turned no more than 0.40 from the camera**) and at least one registered person. Otherwise the face is *not sure* **on purpose**, because a dark, small or sideways face also scores low for people you *do* know. The reason, with the measured number, is on the camera tile, in the server log and on the Events page (*Face not judged: …*). Fix the setup (light, camera at eye level, closer), or loosen that one `FACE__*` setting in `backend/.env` knowing it means more false alarms. It also needs 3 separate sightings in one recording (5 at night) and waits 60 s between alerts for a camera |
| Live video lags or looks choppy | Restart the backend and read its log line `Camera cam1 delivers 1280x720 at 30 fps`. **Low fps** (e.g. 15) usually means the room is dim: laptop cameras halve their frame rate to gather light, so add light. **Very large size** (1920x1080 or more): keep `WEBCAM_WIDTH/HEIGHT` at 1280x720. Close other apps that use the camera (video calls, Photo Booth). Use the dashboard from the same machine or a good network; on weak Wi-Fi MJPEG is bandwidth-hungry |
| Log says `Fire and smoke detection is OFF` | The weights file is missing. Download it as shown in [Fire and smoke detection](#-fire-and-smoke-detection), or ignore it if you do not want the feature |
| Fire/smoke alerts when there is none | Check the snapshot on the alert. Raise `FIRE__SMOKE_CONFIDENCE` / `FIRE__FIRE_CONFIDENCE` (e.g. 0.7) or `FIRE__*_CONFIRM_HITS`, or turn the feature off with `FIRE__ENABLED=false`. Soft, grey, out-of-focus areas and steam are the usual cause |
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
