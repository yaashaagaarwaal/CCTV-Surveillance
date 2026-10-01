# 🛡️ Smart AI-Based CCTV Surveillance System

A modular **AI-powered CCTV surveillance platform** designed for real-time monitoring, intelligent event detection, automated recording, and scalable multi-camera surveillance.

The system combines **computer vision, real-time video processing, event-based recording, and a modern web dashboard** to provide an intelligent surveillance workflow.

---

## ✨ Features

* 📹 **Live CCTV Streaming**
* 📷 **Multi-Camera Support** — Webcam and RTSP/IP cameras
* 🏃 **Motion Detection** using OpenCV MOG2
* 🧍 **YOLO Person Detection** — bounding boxes + confidence, on the live feed
* 🎥 **Event-Based Video Recording**
* 🗄️ **SQLite Event History** — motion events and person-detection events
* ▶️ **Video Playback & Download**
* 🟢 **Camera Online/Offline Monitoring**
* 🔄 **Automatic Camera Reconnection**
* ⚡ **Background Camera + AI Processing** — never blocks the live stream
* 🔔 Designed for real-time security alerts and event classification

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
        Face Recognition          ◄── planned (Phase 6)
              │
        ┌─────┴─────┐
        │           │
      Known       Unknown
        │           │
        ▼           ▼
    Log Event    Trigger Alert    ◄── real-time push alerts planned (Phase 7)
        │           │
        └─────┬─────┘
              ▼
        Event Database (SQLite)   ◄── implemented (events + person_detections)
              │
              ▼
        React Dashboard           ◄── implemented (live feed, boxes, event history)
```

---

## 🏗️ System Architecture

```text
CCTV / IP Cameras
        │
        ▼
 Camera Manager (one background thread per camera)
        │
        ▼
 Motion Detection (OpenCV MOG2)
        │
        ├── no motion ──► Live MJPEG Stream (raw frame)
        │
        ▼ motion found
 YOLO Person Detection (every Nth frame, MPS-accelerated)
        │
        ├──────────────► Live MJPEG Stream (frame + boxes + confidence)
        │
        ▼
 Event Recording (H.264 .mp4)
        │
        ├──────────────► Video Storage (organized by camera/date)
        │
        ▼
 SQLite Event Database (events + person_detections)
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

* React
* Vite
* Tailwind CSS

### Computer Vision

* OpenCV MOG2 background subtraction (motion detection)
* YOLOv8n via Ultralytics — person detection, MPS-accelerated on Apple Silicon
* Face Recognition *(planned, Phase 6)*

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
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/                 events + person_detections tables
│   │   ├── services/
│   │   │   ├── camera/
│   │   │   ├── motion/
│   │   │   ├── detection/      YOLOv8 person detector
│   │   │   └── recording/      motion→YOLO→recording pipeline
│   │   └── main.py
│   └── requirements.txt
│
└── frontend/
    └── src/
        ├── components/
        ├── App.jsx
        └── main.jsx
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

> **First run:** macOS will prompt for camera permission — click **Allow**
> (run the backend in a normal foreground terminal the first time so the
> dialog can appear). Startup also takes a few extra seconds while YOLO
> downloads its weights (first run only, ~6 MB) and warms up the model.

---

## ⚙️ YOLO Detection Settings

All in `backend/app/core/config.py`, under `Settings.detection`:

| Setting | Default | Effect |
|---|---|---|
| `enabled` | `true` | Turns person detection on/off. If the model fails to load, this auto-disables per-camera and motion/recording keep working. |
| `confidence_threshold` | `0.5` | Minimum confidence (0–1) to count as a real person. |
| `imgsz` | `320` | Inference resolution — smaller is faster, less precise. |
| `run_every_n_frames` | `5` | YOLO only runs on every Nth frame **while a motion recording is already active** — the main cost control, so the model never runs at all on an idle scene. |
| `model_path` | `backend/models/yolov8n.pt` | Auto-downloaded on first run if missing. |

Restart the backend after changing any of these. Model inference uses
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
