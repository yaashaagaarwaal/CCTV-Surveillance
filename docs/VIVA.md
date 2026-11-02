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

**Q. Why separate threads per camera, and why two?**
Isolation and simplicity: a bad camera or an exception stays inside its own threads, and the web server
stays responsive. Python's GIL is not a big problem because OpenCV and PyTorch release it while doing the heavy numeric work.
Each camera has a *capture* thread (read a frame, draw the boxes, make the JPEG for the live view) and an
*analysis* thread (motion, recording, YOLO, faces, rules). They are separate on purpose, see the next question.

**Q. Your live video lagged at first. What was wrong and how did you fix it?**
Two things, both found by measuring rather than guessing. (1) One thread did everything, so every YOLO or
face cycle (60-230 ms) froze the picture, and a 1080p webcam frame already cost more than the 50 ms budget
for 20 fps. (2) That thread also *slept* between reads to hold 20 fps, but cameras deliver 30; a driver that
queues frames (RTSP/FFmpeg do) then piles up a backlog, and the picture fell more than a second behind.
Fix: a light capture thread reads at the camera's own speed without ever sleeping or running a model, and
a separate analysis thread always takes the *newest* frame and skips the ones it was too busy for. I also
ask the webcam for 1280x720, which is plenty and cheaper. On a simulated 30 fps camera with real YOLO and
face models running, the live picture went from 17.6 fps and up to 223 ms old (1.35 s old with a queueing
camera) to 30 fps and about 8 ms old, with about the same number of YOLO runs (117 vs 118). A regression test now guards it.
I could only simulate the camera: I did not have the real webcam hardware in the test environment.

**Q. A stranger walked past but no unknown-person alert was raised. Is that a bug?**
Not necessarily, and I checked rather than assumed. The alert needs a face that is clear enough to judge:
at least 48 px wide, bright enough, and facing the camera, because a dark, small or sideways face also scores
low for a person I *do* know. Such faces are reported as "not sure" instead of "unknown". I proved the rest of the
chain works (three confirmations, cooldown, night rule, alert stored, event typed, pushed to the dashboard) with a
test that stops at each stage. What was missing was *explanation*: the reason was never saved. Now each "not sure"
records what was measured against which limit (for example "brightness 31, needs 40"), and the unknown-person alert
states how many checks confirmed it and the similarity score. I did not lower any threshold, because that trades
missed strangers for false alarms about the owner.

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
registration) is pushed to a thread pool so the stream isn't stalled. Camera capture and analysis run in plain background threads.

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
An `AuthProvider` asks `/auth/me` on every page load. React Router guards (`RequireAuth`) send a signed-out visitor to `/login` — no camera image is even requested — and bring them back to the page they wanted after login; signed-in users who open `/login` go to the dashboard. A 401 anywhere logs the user out, and Sign out invalidates the session on the server. Admin-only buttons are hidden for viewers (the server enforces it anyway).

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
One recording. It starts on motion and is *upgraded* to the most serious thing seen: motion → person → suspicious → unknown person → restricted area → smoke → fire. It ends 5 seconds after motion stops (max 30 s per clip; a long visit continues in the next clip).

**Q. What is an alert vs an event?**
An event is "something was recorded". An alert is "someone should look" — with a type, a severity, a message, a snapshot, and an unread → read → resolved lifecycle. Every alert is created through one function, `raise_alert()`, which stores it, pushes it to the WebSocket and notifies channels.

**Q. How do you avoid alert spam?**
Cooldowns per rule, confirmation counts, and de-duplication: a camera outage creates one alert and resolves itself when the camera returns.

**Q. How does fire and smoke detection work, and how much can you trust it?**
A second small YOLOv8 model (fine-tuned on the public D-Fire dataset; classes *fire* and *smoke*) looks at each camera's newest frame once a second, on the analysis thread, so the live picture never waits for it (measured: 30 fps with and without it). One frame never alerts: fire needs 3 detections within 8 s, smoke 5 (and a higher confidence), one alert per episode, with a cooldown, through the same `raise_alert()` as every other alert, with a snapshot and a clip. Trust it as a *hint to go and look*, not as a fire alarm: it was never tested on real fire here, recall is unknown, and we found it calls out-of-focus grey backgrounds "smoke", which is why smoke is stricter.

**Q. Why is smoke stricter than fire?**
Because we measured it: on 401 frames with no fire, the model gave 15 smoke detections (0.51-0.74 confidence) on one clip with a blurry grey background and none anywhere else. Smoke is soft and shapeless, so it is the easier one to imagine. We set the smoke confidence to 0.60 and require 5 detections; this removes that false alarm but could also delay a real one, and we could not measure that without real smoke footage.

**Q. What licence applies to the fire model?**
The model card says AGPL-3.0, inherited from Ultralytics YOLOv8 (the person detector has the same licence). The licence of the D-Fire training data was not checked, so check it before redistributing or using the project commercially.

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

**Q. How does crowd counting work, and is the number exact?**
No, and the app says so. YOLO draws one box per person it can see. I merge duplicate boxes (a box mostly inside a stronger one is the same person),
count the distinct people whose feet are in the picture or in a chosen zone, and show the median of the last five detection cycles so a one-cycle glitch
cannot make a crowd. An alert needs *at least N people for S seconds*, one per crowded episode with a cooldown, and it is worded "at least N" because people who
overlap or stand behind each other are missed. A standard detector cannot count a dense crowd; that needs a density-estimation model. I measured the
effect of merging on a staged clip with four people: without it the detector's boxes made the count 7 and a limit of five fired; with it the count stayed at four.

**Q. Did night enhancement actually help? How do you know?**
I measured it instead of assuming (`scripts/night_benchmark.py`): the same clip at falling brightness with real YOLO. Enhancement costs about 2.5 ms a frame and helps
exactly where raw detection starts failing (85 % to 97 % of frames at 6 % exposure, 37 % to 65 % with heavy noise), and does nothing once the picture is near black.
It added no people to an empty dark room. It also showed a flaw: the "keep whichever pass finds more people" rule could prefer a pass that merely drew a second
box round one person, so duplicates are now merged first. The footage is a darkened copy of a normal clip, not a real night camera, and I have not tested infrared hardware.

**Q. What happens to a timer if the camera drops out?**
Nothing is known about the gap, so it must not be bridged. When a camera is lost the activity monitor is told: visits in progress end, the person tracker and crowd timer
reset, and a person still there afterwards starts a fresh visit, so an outage can never turn 6 s plus a gap plus 6 s into a 10 s loiter. Entries already counted towards
"repeated entry" are kept. A test proves it and fails if that call is removed.

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

**Q. You say it is reliable. How did you check, and what did the check find?**
A final audit ran the real server for 20 minutes with seven cameras (six staged video files with rules, one unreachable RTSP camera) and checked the outcome:
160 alerts, none closer together than their cooldown, none from the empty room, every one with a snapshot and a recording, no error or database lock in the log, and a viewer refused 11 of 11 administrative actions.
It also found real defects, which I fixed and covered with tests that fail without the fix:
(1) a person who walks in *during the 10-second cooldown after a recording* and then stands still produced no motion, so nothing started watching them and no loitering alert fired (1 loitering alert where 4 were expected);
(2) a password mistyped into the username box was written to the log;
(3) a photo that declared gigapixels could force a multi-gigabyte decode;
(4) the crowd counter lost people standing close together at the normal detector size.

**Q. Does the AI slow the video down?**
Measured on a simulated 30 fps camera with the real models: the live picture stayed at 29-30 fps with a 95th-percentile picture age under 10 ms even with face recognition and crowd counting running, while a single AI cycle took up to 0.29 s.
That is by design: capture and analysis are separate threads, so the AI can be slow without ever delaying the picture. Crowd counting cost about 3 CPU points; face recognition about 5.

**Q. How accurate is the crowd count, and why does a crowd camera use a bigger detector input?**
I built frames with a known number of people and counted them. At the normal input size (320 px) people standing shoulder to shoulder were lost (eight people counted as four on average); at 640 px, after merging duplicate boxes, the count was exactly right in every non-overlapping frame for 3, 4, 6 and 8 people, for about 6 ms more per detection.
Once people overlap the count falls fast (eight people overlapping by half average 3.5), so the app always says "at least N". This is the best case: clean cut-outs on a plain room.

**Q. How long between something happening and the alert?**
Measured by playing staged clips in real time and comparing with the earliest moment the footage allows: 0.9-1.2 s for a zone intrusion, 0.7 s for loitering, 0.6 s for a crowd. That is two confirming detection cycles, the median over five cycles for the crowd, and a recording starting. Pushing the alert to the browser added a median 2 ms.

**Q. What have you NOT tested on real hardware?**
Everything with a camera was tested in simulation, because no webcam or phone was available to the test environment: capture from a real webcam, a phone as a camera, infrared hardware, face recognition on real cameras, and a real person at a real angle. Staged clips use cut-out people on a plain room. I also did not run a multi-day soak or a dependency vulnerability scan.

---

## 15. Curveballs

**Q. What if two people walk in together?** YOLO returns one box each; faces are classified independently; one unknown among known people still raises the unknown alert.

**Q. What if the internet is down?** Everything works locally; only the first-time model download and email need internet.

**Q. How would you scale it?** Move the database to PostgreSQL, run detection on a GPU server, share the models via a worker queue, use WebRTC/HLS and an object store for recordings.

**Q. What would you improve next?** Pose estimation for falls, a retention policy for old recordings, push notifications, and a bigger/fine-tuned detection model.

**Q. What is not done?** Audio, PTZ control, mobile app, encryption of stored face data, automatic deletion of old footage (see Known Limitations).
