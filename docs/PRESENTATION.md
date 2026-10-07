# 📊 Presentation Content

Ready-to-paste content for the slides (A–P). Each section is one slide or two; the **bold lines** are
what goes on the slide, the rest is what you say.

---

## A. Project title

**Smart AI-Based Home CCTV Surveillance System**
*Real-time person detection, face recognition, explainable alerts, night surveillance and secure remote monitoring*

Your name · Roll number · Guide's name · College · Year

---

## B. Problem statement

**Traditional CCTV only records. Someone must watch it — or search hours of footage afterwards.**

* Homes rarely have anyone watching the cameras; most footage is empty and wasteful to store.
* Motion alarms fire on shadows, pets and lighting changes, so people stop trusting them.
* Commercial smart cameras need cloud subscriptions and send private video to third parties.
* Remote viewing is often done by opening a port to the internet, which is dangerous.

> "How can a home CCTV system *understand* what it sees — and tell the owner what matters, safely,
> using only hardware they already have?"

---

## C. Objectives

1. Stream several cameras live in one web dashboard.
2. Record only when something happens, and keep a searchable event history.
3. Detect people (not just motion) with a deep-learning model.
4. Recognize registered people and flag unknown ones.
5. Raise explainable alerts: unknown person, restricted-area intrusion, loitering, repeated entry, unusual hours, camera offline.
6. Keep working at night, and be honest about its limits.
7. Protect everything with authentication and support secure remote monitoring.
8. Run entirely on a personal computer, with no cloud.

---

## D. Proposed solution

**A local AI pipeline: motion → person → face → rules → alert.**

* Cheap motion detection decides *when* to look; YOLO decides *what* is there; a face model decides *who*; clear rules decide *whether to alert*.
* One Python backend (FastAPI + OpenCV) processes every camera in its own thread and stores everything in SQLite and local files.
* A React dashboard shows live video, events, recordings and real-time alerts.
* Security is built in: login, roles, hashed passwords, CSRF protection, and a deployment plan that never exposes the machine directly.

---

## E. System architecture

```text
 Cameras (webcam · RTSP/IP · HTTP · video files)
        │ one thread per camera
        ▼
 ┌──────────────────────── Processing pipeline ────────────────────────┐
 │ Lighting → Motion (MOG2) → Recording → YOLOv8n → Face → Rules → Alert│
 └─────────────┬───────────────────────────────────────┬───────────────┘
               ▼                                       ▼
        SQLite + local files                     Alert bus ──► WebSocket ──► Dashboard
               ▲                                       │                      (email optional)
               │            FastAPI (REST · MJPEG · WebSocket, login required)
               └──────────────────────────┬────────────┘
                                          ▼
                              React dashboard (browser)
```

Remote access: **browser → VPN / HTTPS proxy → FastAPI on 127.0.0.1** (never a directly exposed port).

---

## F. Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, **FastAPI**, Uvicorn, SQLAlchemy |
| Computer vision | **OpenCV** (capture, MOG2, drawing, video writing, face models), **YOLOv8n** (Ultralytics / PyTorch, Apple-Silicon GPU) |
| Face recognition | **YuNet** detection + **SFace** 128-number embeddings |
| Database | **SQLite** (11 tables) |
| Frontend | **React**, React Router, Vite, Tailwind CSS |
| Real-time | MJPEG video streaming, WebSocket alerts |
| Security | scrypt password hashing, cookie sessions, CSRF/CORS/Host checks, optional HTTPS proxy |
| Size | ~5,200 lines of backend code, ~3,800 lines of frontend code, ~1,200 lines of tests/scripts |

---

## G. Major modules

| # | Module | Responsibility |
|---|---|---|
| 1 | **Camera manager** | Opens each source, runs one worker thread per camera, reconnects automatically, reports status |
| 2 | **Motion detection** | OpenCV MOG2 background subtraction with noise, shadow and lighting-jump handling |
| 3 | **Person detection** | Shared YOLOv8n model, "person" class only |
| 4 | **Face recognition** | Face detection, embeddings, known / unknown / not-sure decision, unknown-person tracker |
| 5 | **Night module** | Detects low light / infrared; denoising and contrast enhancement for detection |
| 6 | **Activity rules** | Restricted zones, loitering, repeated entry, security hours, fall-like |
| 7 | **Recording & events** | H.264 clips, event lifecycle, crash recovery |
| 8 | **Alert system** | `raise_alert()`, severity, lifecycle, WebSocket bus, email channel |
| 9 | **Security** | Authentication, roles, sessions, throttling, middleware |
| 10 | **REST API** | 49 REST endpoints + a WebSocket |
| 11 | **Dashboard** | 8 pages: dashboard, cameras, events, recordings, alerts, people, users, login |

---

## H. AI / computer-vision pipeline

```text
Frame ─► Lighting (day / night / IR)
      ─► Motion detection ─────────── none ──► just show the live view
              │ motion
              ▼
        Start recording (raw video)
              │ every 5th frame
              ▼
        YOLOv8n  (person, ≥ 50 % confidence)
              │ people
              ├──► Face detection ─► 128-number embedding ─► cosine similarity
              │        ≥ 0.40 known │ < 0.25 unknown (3 confirmations) │ else "not sure"
              └──► Rules: zone intrusion · loitering · repeated entry · security hours · fall-like
                                  │
                                  ▼
                     Snapshot + Alert (severity, reason, recording)
```

Key ideas to mention: *cheap check first, expensive model second*; *never alert on a single frame*;
*"not sure" instead of guessing*; *recordings are raw, overlays only on the live copy*; *night enhancement cannot create missing information*.

---

## I. Database design

11 tables in one SQLite file:

```text
cameras ─< zones          people ─< face_samples (embeddings)
   └────< camera_rules          └─< face_observations >─ events
events ─< person_detections                              events ─< alerts
users ─< user_sessions
```

| Table | Holds |
|---|---|
| `cameras`, `zones`, `camera_rules` | configuration set from the dashboard |
| `events`, `person_detections` | every recording and YOLO sighting |
| `people`, `face_samples`, `face_observations` | registered people, their embeddings, every face seen |
| `alerts` | type, severity, message, JSON details, snapshot, read/resolved state |
| `users`, `user_sessions` | accounts (hashed passwords) and sessions (hashed tokens) |

Design choices: no foreign key from events to cameras (deleting a camera keeps history); embeddings
stored as binary vectors, not photos; automatic schema upgrade at start-up.

---

## J. Working flow

1. **Start-up:** load settings → create/upgrade database → create admin → load YOLO & face models → start every enabled camera.
2. **Per camera, per frame:** read → lighting check → motion check.
3. **Motion:** start an MP4 and a database event; every 5th frame run YOLO.
4. **Person found:** event becomes a *person* event → faces are matched → rules are evaluated.
5. **Something notable:** save a snapshot → `raise_alert()` → database + WebSocket (+ email).
6. **No motion for 5 s:** close the recording, mark the event completed.
7. **Dashboard:** live MJPEG, polling for status, WebSocket for instant alerts; user plays recordings, resolves alerts.

---

## K. Key features

* Live multi-camera dashboard · motion-triggered H.264 recording · event history with filters
* YOLO person detection · face recognition · unknown-person alerts
* Restricted zones · loitering · repeated entry · security hours · experimental fall-like — **each alert explains itself**
* Night / infrared detection and NIGHT MODE indicator
* Alerts with severity, read/resolve, real-time push, browser + email notifications
* Login, admin/viewer roles, hardened API, secure remote-access design
* Reliability: isolated cameras, auto-reconnect, safe shutdown, crash recovery

---

## L. Testing methodology

| Level | How | Result |
|---|---|---|
| **End-to-end system test** | Starts the real server on a temporary database, adds 4 video cameras + 1 broken one, then checks the whole system through the API | **116 / 116 checks passed** |
| **Rule tests** | Each suspicious-activity rule with positive and negative cases and a controlled clock; deliberately broken rules to prove the tests catch them | **16 / 16 passed** |
| **Pipeline test** | Scripted people through the real motion → recording → detection pipeline | **3 / 3 passed** |
| **Security test** | Walks every route: login required, writes need admin | **3 / 3 passed** (49 route/method combinations) |
| **Frontend** | Lint + production build; manual walkthrough of every page | clean |
| **Clean-install test** | New virtualenv + `npm ci` from the pinned files | pass |

The test suite also found and fixed real bugs (e.g. camera passwords visible to viewer accounts;
unprotected routes in an earlier version; a false motion event when lights switched).

---

## M. Expected results / results achieved

| Capability | Result |
|---|---|
| Multi-camera live streaming | 4 simultaneous cameras + 1 failing camera, all independent |
| Motion → person → recording | Every demo camera produced a person event with a playable, seekable MP4 |
| Person confidence | ~90–96 % on the demo footage (day and night) |
| Face recognition | Same person 0.64–0.96 similarity; different person 0.02–0.27; unknown person alerted only after 3 confirmations |
| Night detection | People found in ~97 % / 83 % / 56 % of moderate / dark / very dark frames (raw only: 97 / 82 / 21 %) |
| Suspicious-activity rules | All 5 rules fire correctly, with explanation, severity, snapshot and recording |
| Alerts | Stored, filterable, real-time over WebSocket, one alert per camera outage (auto-resolved) |
| Security | 100 % of routes require login; throttling, CSRF and role checks verified |
| Reliability | Clean Ctrl+C, data intact after restart, no recording left half-written |

Present these as *measured on the test setup*, not as general accuracy claims.

---

## N. Limitations

* Face recognition is statistical — not 100 % accurate, no spoof (photo) protection.
* Night detection is weaker; enhancement cannot recover lost information.
* "Suspicious" = configurable rules, not understanding of intent; fall-like rule is experimental.
* YOLOv8n is the smallest model; detection only runs when there is motion.
* MJPEG streaming is bandwidth-heavy and has no audio; SQLite and one machine limit scale.
* No automatic deletion of old recordings, no mobile app or push notifications yet.

---

## O. Future scope

* Pose estimation for reliable fall detection · retention / archiving policy · disk-usage monitoring
* Push notifications (Telegram / mobile) · WebRTC / HLS streaming with audio
* Larger or fine-tuned models, GPU server, multi-camera tracking
* Analytics (heatmaps, busiest hours), encrypted face data, two-factor login, Docker packaging

---

## P. Conclusion

**A complete, working, locally-run smart CCTV system that detects people, recognizes faces, explains its alerts, works at night and is secure by design.**

* Integrates computer vision, a web API, a database and a modern UI into one system.
* Prioritizes honesty: clear rules instead of vague "AI", "not sure" instead of guessing, limits documented.
* Fully tested end to end and reproducible from a clean install.

*Thank you — questions?*
