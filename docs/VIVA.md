# 🎤 Viva Preparation

Short, honest answers you can say out loud. Numbers are the real settings in this project
(`backend/app/core/config.py`). If you are unsure of something, say what the system *does* — never
claim it is perfect.

**The 30-second answer to "what did you build?"**
> "A home CCTV system that watches several cameras, records only when there is motion, uses YOLO to
> find people and a face model to tell known people from strangers, raises alerts with a reason and a
> snapshot, works at night, and is protected by login so it can be reached remotely and safely. It all
> runs on my own computer with FastAPI, OpenCV, SQLite and a React dashboard."

---

## 1. Overall project

**Q. Why this project / what problem does it solve?**
Ordinary CCTV only records; someone has to watch or search hours of footage. This system watches for
you: it records only events, says *who/what* it saw, and alerts you about strangers or restricted-area
intrusions. Data stays at home (no cloud subscription, better privacy).

**Q. Explain the architecture.**
React dashboard ⇄ FastAPI backend ⇄ per-camera worker threads ⇄ SQLite + local files. Each camera
thread runs: lighting check → motion detection → (if motion) recording → YOLO person detection →
face recognition → activity rules → alert. Alerts go to the database, to the browser over a WebSocket,
and optionally to email.

**Q. Why one thread per camera?**
Isolation and simplicity: a bad camera or an exception stays inside its own thread, and the web server
stays responsive. Python's GIL is not a big problem because OpenCV and PyTorch release it while doing the heavy numeric work.

**Q. What was the hardest part?**
Reducing false alarms honestly: lighting changes looked like motion, a turned face looked like a stranger,
and night enhancement sometimes made detection *worse*. I fixed these with a lighting-jump reset, a
"not sure" category for poor faces, and a raw-vs-enhanced strategy that keeps whichever finds more people —
all measured, not guessed.

---

## 2. OpenCV

**Q. What is OpenCV and where do you use it?**
An open-source computer-vision library. I use it to: read frames (webcam / RTSP / video file), do motion
detection (MOG2), draw boxes and zones, encode JPEGs for the live stream, write H.264 MP4 recordings,
run the face detector (YuNet) and recognizer (SFace) through its DNN module, test whether a point is
inside a polygon (`pointPolygonTest`), and enhance dark frames (CLAHE).

**Q. How does an image look to the program?**
A NumPy array of shape height × width × 3, values 0–255, in BGR order.

**Q. What is CLAHE?**
Contrast-Limited Adaptive Histogram Equalization: it boosts contrast in small tiles of the image
without blowing out noise too much. I apply it (plus a gamma curve) to the brightness channel of dark frames.

---

## 3. Motion detection

**Q. How does your motion detection work?**
OpenCV **MOG2** background subtraction. For every pixel it keeps a mixture of Gaussian distributions
describing what that pixel normally looks like. A pixel that doesn't fit is "foreground". I then
remove shadows, clean noise with morphological open/dilate, find contours, and call it motion only if a
blob is larger than `min_area` (3000 px).

**Q. Why not simple frame differencing?**
Differencing compares two frames, so it fires on lighting flicker and misses slow movers. MOG2 *learns*
the background and keeps adapting, so sunlight drifting across a room becomes background.

**Q. How do you avoid false positives?**
`varThreshold` 30 (less sensitive than the default 16), minimum blob area, a 30-frame warm-up, shadow
removal, and a **lighting-jump reset**: if average brightness changes by more than 30 levels in one go
(lights switched) the model is relearned instead of raising an event. At night frames are slightly blurred first because sensor grain looks like motion.

**Q. Why run motion detection before YOLO?**
Cost. Motion costs milliseconds; YOLO is far heavier. YOLO runs only while a recording is active, and
only every 5th frame. An empty scene costs almost nothing, so several cameras fit on a laptop.

---

## 4. YOLO / person detection

**Q. What is YOLO?**
"You Only Look Once": a single neural network that looks at the whole image once and directly predicts
bounding boxes and class probabilities — unlike older two-step detectors (R-CNN) that first propose regions then classify. That's why it's fast enough for video.

**Q. Which version and why?**
YOLOv8 **nano** (`yolov8n`, ~3 million parameters), pretrained on the COCO dataset (80 classes). I keep
only class 0, *person*. Nano is the fastest; the trade-off is lower accuracy on small or partly hidden people.
I didn't train it — a pretrained model is sufficient for "is there a person".

**Q. What do confidence and NMS mean?**
Confidence (0–1) is how sure the model is; I require ≥ 0.5. Non-Maximum Suppression removes duplicate
overlapping boxes for the same person (keeps the best one).

**Q. Why 320 px input and every 5th frame?**
Speed. At ~20 fps, every 5th frame is ~4 checks per second — enough for a person walking. 320 px is
fast and adequate for people near the camera. Both are configurable.

**Q. Does it use the GPU?**
On Apple Silicon it uses MPS automatically; otherwise CPU. One model instance is shared by all cameras behind a lock.

**Q. How accurate is it?**
Good on clear daytime people; weaker for tiny, hidden or very dark people. At night I measured about 97 % / 83 % / 56 % of people found in moderate / dark / very dark frames.

---

## 5. Face recognition

**Q. Detection vs recognition?**
Detection answers "where is a face?" (YuNet). Recognition answers "whose face is it?" (SFace).

**Q. How does recognition work?**
SFace is a neural network that converts a face into an **embedding** — 128 numbers. Two photos of the same person give vectors pointing in a similar direction. I compare a live face with every registered
embedding using **cosine similarity**. ≥ 0.40 → *known*; < 0.25 → *unknown*; in between → *not sure*.

**Q. Why a "not sure" category?**
A small, dark or turned-away face naturally scores low; calling it a stranger would raise false alarms.
Such faces are logged but never alert. An unknown-person alert also needs 3 separate confirmations in one recording.

**Q. What do you store about a registered person?**
Only the 128-number embedding (SQLite) and a 200 px thumbnail. The uploaded photo is not kept. Data is
owner-only on disk and nothing leaves the computer.

**Q. Can it be fooled / is it 100 % accurate?**
No. Lighting, angle, distance and look-alikes affect it, and it has no liveness check, so a printed photo could fool it. It's a helper, not proof of identity.

**Q. Why is the threshold strict?**
Calling a stranger "known" is the costly mistake, so `known_threshold` (0.40) is higher than OpenCV's suggested 0.363.

---

## 6. Computer-vision pipeline

**Q. Walk me through one frame.**
Capture → lighting analysis (day/night/IR) → motion (MOG2) → if motion, write the raw frame to the
recording → every 5th frame YOLO → for each person, face detection + embedding + match → activity rules →
if a rule or unknown face fires, save a snapshot and raise an alert → draw boxes on a *copy* for the live view.

**Q. Why is the recording not annotated?**
Evidence should be untouched. Overlays are drawn only on the copy sent to the dashboard.

**Q. How does night mode work, and what are its limits?**
Brightness is smoothed and compared with two thresholds (55 on / 75 off, so it doesn't flicker). Low colour variation with decent brightness means infrared. At night YOLO runs on the raw *and* an enhanced copy and keeps the better result. **Enhancement cannot create information that isn't there** — it only re-maps what the camera captured and amplifies noise, so very dark footage is still unreliable.

---

## 7. FastAPI (backend)

**Q. Why FastAPI?**
Fast, modern and typed: automatic request validation (Pydantic), automatic Swagger docs, dependency
injection (my login check is a dependency), native async for streaming, and WebSocket support.

**Q. Where do you use async and where normal functions?**
The MJPEG stream and WebSocket are `async` (many viewers cost almost nothing). CPU-heavy work (face
registration) is pushed to a thread pool so the stream isn't stalled. Camera processing is in plain background threads.

**Q. How are APIs protected?**
Every router has a `current_user` dependency (cookie session); mutating routes need `require_admin`. A test walks all routes and fails if one is unprotected.

**Q. What is middleware here?**
Code that wraps every request: Host check, security headers, CORS, and an Origin check that blocks cross-site (CSRF) writes and WebSockets.

---

## 8. React (frontend)

**Q. Why React?**
Component-based UI that re-renders when data changes — ideal for a live dashboard. Vite gives a fast dev server; Tailwind gives consistent styling.

**Q. How does the dashboard get live data?**
Camera status is polled every few seconds (`usePolling`); alerts arrive instantly over a **WebSocket** with a polling fallback; video is an `<img>` pointing at the MJPEG stream.

**Q. How does login work in the UI?**
An `AuthProvider` asks `/auth/me` on load; no session → only the login form is rendered (no camera image is even requested). A 401 anywhere logs the user out. Admin-only buttons are hidden for viewers (the server enforces it anyway).

---

## 9. SQLite / database

**Q. Why SQLite?**
Zero setup, a single file, ACID transactions, and plenty for a home system. Trade-off: one writer at a time and one machine; for many cameras I'd move to PostgreSQL (SQLAlchemy makes that a small change).

**Q. Main tables?**
`cameras`, `events` (one per recording), `person_detections`, `people`, `face_samples` (embeddings), `face_observations`, `alerts`, `zones`, `camera_rules`, `users`, `user_sessions`.

**Q. How are embeddings stored?**
As a BLOB of 128 floats per registered face; the gallery is loaded into memory for fast matching.

**Q. Why no foreign key on `events.camera_id`?**
So deleting a camera keeps its history and recordings.

**Q. Concurrency?**
Each operation opens its own short session; many camera threads can write safely. SQLite serializes writes, which is fine at this scale.

---

## 10. Video streaming and recording

**Q. How does live video reach the browser?**
**MJPEG**: the server keeps the latest frame of each camera as a JPEG and streams them as a
`multipart/x-mixed-replace` HTTP response; the browser's `<img>` tag simply keeps replacing the picture. Simple and works everywhere.

**Q. Why not WebRTC or HLS?**
They are more efficient and support audio but need much more infrastructure. MJPEG is fine for a few local cameras; it's listed as a future improvement. Browsers allow only ~6 connections per site, so beyond 4 cameras the dashboard refreshes snapshots instead.

**Q. How are recordings stored and played?**
OpenCV writes H.264 MP4 (`avc1` — browsers can't play the older `mp4v`). Files are in `storage/recordings/<camera>/<date>/`. The server answers HTTP Range requests so the player can seek.

**Q. What if the server crashes mid-recording?**
On the next start such events are closed out: `interrupted` if the file is readable, otherwise `failed`. A clean Ctrl+C also finalizes them.

---

## 11. Event detection and alerts

**Q. What is an event?**
One recording. It starts on motion and is *upgraded* to the most serious thing seen: motion → person → suspicious → unknown person → restricted area. It ends 5 seconds after motion stops (max 30 s per clip; a long visit continues in the next clip).

**Q. What is an alert vs an event?**
An event is "something was recorded". An alert is "someone should look" — with a type, a severity, a message, a snapshot, and an unread → read → resolved lifecycle. Every alert is created through one function, `raise_alert()`, which stores it, pushes it to the WebSocket and notifies channels.

**Q. How do you avoid alert spam?**
Cooldowns per rule, confirmation counts, and de-duplication: a camera outage creates one alert and resolves itself when the camera returns.

---

## 12. Suspicious activity

**Q. Can your system tell if behaviour is suspicious?**
No — and I don't claim it can. What is suspicious depends on the home. It checks **clear, configurable rules** and says exactly which fired.

**Q. Which rules?**
1. *Zone intrusion* — a person's feet are inside a polygon the owner drew.
2. *Loitering* — a visit inside a zone longer than its limit (e.g. 30 s).
3. *Repeated entry* — N separate entries into a zone within a time window (leaving = zone empty for 4 s).
4. *Security hours* — any person during hours the owner sets.
5. *Fall-like* (experimental) — a person's box goes from upright to lying within 3 s and stays down 4 s.

**Q. Why "feet" and not the whole box?**
A person's position on the floor is where their feet are; the box centre can be "inside" a zone while the person is outside it.

**Q. Show me an explanation.**
"Person remained in restricted zone 'Driveway' for 32 seconds (limit 30 seconds)" — plus time, camera, severity, detector confidence, snapshot and recording.

**Q. Limitations of the fall rule?**
It only sees a rectangle (no pose), so it can miss falls (hidden, overhead camera) and fire if someone lies down fast. A person who is first seen already lying never triggers it. That's why it's off by default and worded "possible fall".

---

## 13. Security and remote access

**Q. Is it safe to expose?**
Not directly — and I deliberately don't. It listens on `127.0.0.1`, requires login, and for remote use I recommend a private VPN (Tailscale/WireGuard) or an HTTPS reverse proxy. `REMOTE_MODE=true` makes the server refuse to start unless hosts, HTTPS origins, a strong secret and a strong admin password are configured.

**Q. How are passwords and sessions handled?**
Passwords: scrypt hash with a salt (never stored in plain text). Sessions: a random token in an `HttpOnly`, `SameSite=Strict` cookie; only a keyed hash of the token is stored server-side. Login is throttled (5 failures → 5 min lock). RTSP passwords are masked and hidden from viewer accounts.

---

## 14. Testing

**Q. How did you test it?**
An end-to-end script starts the real server on a temporary database, adds the demo cameras, and checks over 110 things through the API (login, roles, streaming, detection, recording playback, faces, every rule, alerts, WebSocket, errors, shutdown, restart). Separate tests cover each suspicious-activity rule with positive and negative cases, route protection, and the frontend lint/build. Where a test found a real bug, I fixed it (e.g. RTSP passwords were visible to viewers).

**Q. Did you measure accuracy?**
For night detection and face similarity, yes, on test data (see README). I did not run a large formal benchmark; results depend on your cameras and lighting.

---

## 15. Curveballs

**Q. What if two people walk in together?** YOLO returns one box each; faces are classified independently; one unknown among known people still raises the unknown alert.

**Q. What if the internet is down?** Everything works locally; only the first-time model download and email need internet.

**Q. How would you scale it?** Move the database to PostgreSQL, run detection on a GPU server, share the models via a worker queue, use WebRTC/HLS and an object store for recordings.

**Q. What would you improve next?** Pose estimation for falls, a retention policy for old recordings, push notifications, and a bigger/fine-tuned detection model.

**Q. What is not done?** Audio, PTZ control, mobile app, encryption of stored face data, automatic deletion of old footage (see Known Limitations).
