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
│       │   └── health.py
│       ├── db/                 SQLAlchemy models + session setup (added in Phase 2)
│       ├── services/            camera capture / detection / recording logic
│       └── storage/              recorded video clips + snapshots (gitignored)
└── frontend/                  React 19 + Vite + Tailwind CSS 4
    └── src/
        ├── main.jsx
        ├── App.jsx            dashboard shell
        └── index.css          Tailwind entry point
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

## Project phases

- [x] **Phase 1 (this delivery):** project scaffold, health-check API,
      dashboard shell that confirms frontend ↔ backend connectivity.
- [ ] Phase 2: camera capture (OpenCV) + live MJPEG/WebSocket feed, multi-camera support
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

## What was intentionally left out of Phase 1

No OpenCV, YOLO, face recognition, or database models yet — those are
Phase 2+. Adding them now would mean testing multiple new moving parts at
once instead of verifying each layer works before building on it.
