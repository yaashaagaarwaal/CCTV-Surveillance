# 🛡️ Smart AI-Based CCTV Surveillance System

A modular **AI-powered CCTV surveillance platform** designed for real-time monitoring, intelligent event detection, automated recording, and scalable multi-camera surveillance.

The system combines **computer vision, real-time video processing, event-based recording, and a modern web dashboard** to provide an intelligent surveillance workflow.

---

## ✨ Features

* 📹 **Live CCTV Streaming**
* 📷 **Multi-Camera Support** — Webcam and RTSP/IP cameras
* 🏃 **Motion Detection** using OpenCV MOG2
* 🎥 **Event-Based Video Recording**
* 🗄️ **SQLite Event History**
* ▶️ **Video Playback & Download**
* 🟢 **Camera Online/Offline Monitoring**
* 🔄 **Automatic Camera Reconnection**
* ⚡ **Background Camera Processing**
* 🤖 Extensible AI pipeline for intelligent surveillance
* 🔔 Designed for real-time security alerts and event classification

---

## 🧠 AI Surveillance Pipeline

The system is designed to evolve from basic motion detection into an intelligent computer-vision surveillance pipeline:

```text
              CCTV / IP Camera
                     │
                     ▼
             Frame Acquisition
                     │
                     ▼
             Motion Detection
                (OpenCV)
                     │
                     ▼
             Object Detection
                 (YOLO)
                     │
              ┌──────┴──────┐
              │             │
           Person        Other Object
              │
              ▼
        Face Recognition
              │
        ┌─────┴─────┐
        │           │
      Known       Unknown
        │           │
        ▼           ▼
    Log Event    Trigger Alert
        │           │
        └─────┬─────┘
              ▼
        Event Database
              │
              ▼
        React Dashboard
```

---

## 🏗️ System Architecture

```text
CCTV / IP Cameras
        │
        ▼
 Camera Manager
        │
        ├──────────────► Live MJPEG Stream
        │
        ▼
 Motion Detection
        │
        ▼
 Event Recording
        │
        ├──────────────► Video Storage
        │
        ▼
 SQLite Event Database
        │
        ▼
 React Dashboard
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

* OpenCV MOG2
* Background Subtraction
* YOLO *(AI detection layer)*
* Face Recognition *(planned AI layer)*

### Storage

* SQLite
* Local MP4/H.264 video storage

---

## 📁 Project Structure

```text
CCTV-Surveillance/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── services/
│   │   │   ├── camera/
│   │   │   ├── motion/
│   │   │   └── recording/
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

---

## 🔮 Future Enhancements

* 🎯 YOLO-based person and object detection
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
