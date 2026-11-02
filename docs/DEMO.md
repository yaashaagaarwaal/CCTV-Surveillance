# ▶️ Demo Guide

**Part 0 is the checklist for your faculty demonstration (about 12 minutes).** Parts A–D are the original 4-minute script
and its preparation, and Part E explains how to test every rule with only your MacBook webcam and phone. Rehearse twice.

---

## 0. Faculty demonstration: the checklist

**How to read the labels.** Be open about them in front of the faculty: it is a strength, not a weakness.

| Label | Meaning |
|---|---|
| 🟢 **LIVE** | Happens in front of them with your webcam (or phone). Nothing is prerecorded |
| 🟡 **STAGED** | A real detection on a live camera, but you act the scene out (walk into a zone, stand still) |
| 🔵 **PRERECORDED** | A video file is played as if it were a camera. Say so out loud |
| 🔴 **NOT VERIFIED ON REAL HARDWARE** | Tested in simulation only (no real webcam or phone was available during testing); rehearse it first |

### Before they arrive (15 minutes)

- [ ] `chmod 600 backend/.env` (the server warns at start-up if your passwords file can be read by other users)
- [ ] Start the backend and the frontend (commands in Part A below); open `http://localhost:5173`
- [ ] Allow the macOS camera permission for your terminal once; add the **Local webcam** (source `0`) and check the backend log prints `Camera … delivers 1280x720 at 30 fps` (about 15 fps means the room is too dark)
- [ ] **People → register yourself** (3 clear, front-facing, well-lit photos or *Use camera*)
- [ ] Add these file cameras (*Cameras → Add camera → Video file*): `demo_crowd.mp4` named **Crowd clip** and `demo_lowlight_zone.mp4` named **Dim room clip**. Run `python scripts/make_demo_videos.py` first if they are missing
- [ ] **Crowd clip → (!) → "Alert when at least 3 people stay for 8 s"** → Save rules. **Dim room clip → (!) → draw the zone on the right half** → Save
- [ ] **Webcam → (!) → draw a zone** over one side of the floor, *loitering after 10 s*, *repeated entry 2 within 5 min* → Save
- [ ] Put `ACTIVITY__ZONE_ALERT_COOLDOWN_SECONDS=20` in `backend/.env` and restart, so an intrusion can be repeated without a 2-minute wait
- [ ] Alerts → **Mark all read**, so new alerts stand out. Close other apps that use the camera
- [ ] Record one good run with QuickTime as a backup

### The demonstration

| # | Min | What you do | What they should see | Label | If it does not work |
|---|---|---|---|---|---|
| 1 | 1 | Open the site, click **Login**, sign in. Walk through the dashboard counters, the camera tiles and the **monitoring strip** under each tile | Landing page → login → dashboard; *System online*, *Live alerts* chip; tiles show LIVE and which rules are active | 🟢 | Backend not running: check Terminal 1 |
| 2 | 1 | Show **two cameras**: your webcam and a second source | Both tiles LIVE. Use your phone as a webcam (Part E3) if you have set it up; otherwise use `demo_entrance.mp4` and say "this is a recorded video acting as a second camera" | 🟢 webcam · 🔴 phone · 🔵 video file | Skip the phone; the video camera is independent of it |
| 3 | 1.5 | Step into the webcam's view. Then show an **unknown person** | Blue box `person 9x%`, your **name in green** (face recognition). Unknown: ask a classmate to face the camera for about 5 s: red **UNKNOWN**, a toast, and an alert with its explanation. Or use `demo_entrance.mp4` (the man in it is not registered) | 🟢 you · 🟡 classmate · 🔵 clip · 🔴 faces on your hardware | An orange *NOT SURE · reason* is **honest behaviour**: read the reason aloud ("too dark", "turned away") and fix the light |
| 4 | 1.5 | **Restricted area:** walk so the lower part of your body enters the zone you drew | A *Restricted area* alert within about 1–2 s, with a snapshot and "Person entered restricted zone …". Standing there does not repeat it | 🟡 | Make sure the camera sees your lower body; or play `demo_zone_entry.mp4` (🔵) |
| 5 | 1 | **Loitering:** stay inside the zone for 10 s | A *Loitering* alert saying how long you stayed ("remained … for 10 seconds (limit 10 seconds)") | 🟡 | Or `demo_zone_loiter.mp4` (🔵) |
| 6 | 1.5 | **Crowd counting:** show the **Crowd clip** tile | The tile counts up to **4+ in view / limit 3**; a *Crowd* alert about 20 s into the clip saying "At least 4 people …". Say: "staged cut-out people: one person cannot make a crowd live; the count is *at least*, because overlapping people are missed" | 🔵 | Wait for the clip to loop (30 s) |
| 7 | 1 | **Night:** show the **Dim room clip** tile | **NIGHT MODE** badge; the intruder is still found and the zone alert fires. Show the night table in the README: "synthetic darkening, no infrared hardware was tested" | 🔵 (optionally 🟢 with the lights off) | Real darkness works only down to a point; the table shows where it stops |
| 8 | 1 | **Alert history and evidence:** open Alerts, then Events | Each alert: severity, time, snapshot, the **explanation**; *Recording* plays the clip; Events lists timestamps and *why it was flagged* | 🟢 | |
| 9 | 1 | **Disconnection and recovery:** Cameras → add a camera with the address `rtsp://127.0.0.1:9/x` | It shows **Offline** while the other cameras carry on; a *Camera offline* alert appears after about 20 s; **disable** it and the alert resolves by itself. For a real webcam: change its source to `9` (fails) and back to `0` (recovers) | 🟡 · 🔴 webcam recovery | The recovery path is covered by an automated test with a network stream |
| 10 | 1.5 | **Limitations and measured performance** (use the slide / README) | The numbers in the table below, and the limitations list | 🟢 | |

### What to say about performance (all measured; see the README for the conditions)

Measured on an Apple M3 (8 cores, 8 GB) with a simulated 30 fps 720p camera and the real models; none of it is from a real camera:

* the **live picture stays at 30 fps with a picture age under 10 ms (p95)** even with face recognition and crowd counting running, because the AI runs on a separate thread and can be slow without ever delaying the video;
* alerts fire **about 0.5–1.2 s after the earliest moment the footage allows**;
* a **10-minute run of 7 cameras** produced no duplicate alert, no false alert in an empty room, and no error in the log.

### What to say about limitations

* Face recognition is statistical and refuses to guess ("not sure") when a face is small, dark or turned away.
* A crowd count is **"at least N"**; overlapping people are missed (the README shows by how much).
* Night detection works down to a point and **infrared hardware was not tested**.
* The fall-like rule is experimental, off by default, and must not be used as a safety device.
* Everything was developed and tested on one Mac, with no real CCTV camera.

---

## A. Preparation — do this 10 minutes before (not during) the demo

**1. Start the system** (two terminals):

```bash
# Terminal 1 – backend
cd backend && source venv/bin/activate
uvicorn app.main:app --port 8000          # no --reload: more stable for a demo

# Terminal 2 – frontend
cd frontend && npm run dev                # open http://localhost:5173
```

(or the single-terminal mode: `npm run build` once, then
`SECURITY__SERVE_FRONTEND=true uvicorn app.main:app --port 8000` and open http://127.0.0.1:8000)

Open http://localhost:5173 (the homepage), click **Login**, and sign in as `admin` (the password you put in `backend/.env`). You land on the dashboard at `/dashboard`.

**2. Add the demo cameras** — Cameras → *Add camera* → type **Video file (loops)**:

| Name | File |
|---|---|
| Front Entrance | `demo_entrance.mp4` |
| Street View | `demo_street.mp4` |
| Night Camera | `demo_night.mp4` |

(Run `python scripts/make_demo_videos.py` first if the files are not listed.) Keep the **Local Webcam**
camera too; allow the macOS camera permission once beforehand.

**3. Register yourself** — People → *Register person* (your name) → **Use camera** on *Local Webcam*, look
at the camera, capture 3 times (slightly different head angles). *Why:* the man walking through the
"Front Entrance" video is a stranger to the system, so he will be reported as an **unknown person**.

> No webcam? People → your name → *Add photos* → upload a clear, front-facing selfie. For a quick
> recognition-by-name demo you can instead upload `backend/sample_videos/demo_person.jpg` (the larger
> man in the Front Entrance video); he is then shown by name, but you won't get an unknown-person alert from the videos.

**4. Draw one restricted zone** — Cameras → octagon **(!)** button on *Front Entrance*. Click the four
**corners of the picture, right to the edges** (the people in the demo video are close-ups, so their
feet are at the bottom edge), name it **"Restricted – Garage"**, leave severity *high*, set
**loitering after 10 seconds**, **repeated entry 2 within 5 minutes**, *Save zone*.
Optional: tick *security hours* to cover the current time (e.g. from one hour ago to one hour ahead) and *Save rules*.

**5. Let it run for 2–3 minutes** so the Events, Recordings and Alerts pages already contain data.
Then on the Alerts page click **Mark all read** so new alerts stand out.

**Pre-flight check (30 seconds):** Dashboard shows all cameras `LIVE`; Night Camera shows **NIGHT MODE**;
Alerts page has entries; Events page has "Why this was flagged" lines.

---

## B. The demo (≈ 4 minutes)

| Time | Show | Say | Proves |
|---|---|---|---|
| **0:00** | **Dashboard.** Point at the counters and the camera tiles (LIVE / REC badges). | "This is the control room. Four cameras stream live over MJPEG, each in its own threads, so one failure can't stop the others, and the AI never makes the picture lag. The badges show live, recording, and people in view." | Live CCTV · multiple cameras · dashboard |
| **0:25** | Walk in front of the **webcam tile**. Point at the box, `person 9x%`, then your **name** in green. | "Motion detection wakes up YOLO, which finds the person; then the face model recognizes me as a registered person. Recording started automatically — see REC." | Motion · YOLO · face recognition · recording |
| **0:55** | Wait for / point at the **Front Entrance** tile: **UNKNOWN** red box, then the bell badge / toast appears. Click it → **Alerts page**. | "The man in this video isn't registered, so he is classified unknown — after 3 confirmations, so one blurry frame can't raise an alarm. Here is the alert: severity, time, snapshot, and a link to the recording." Click **Recording** to play it; click **Resolve**. | Unknown-person detection · alerts · event recording/playback |
| **1:40** | On the Alerts page, open the **restricted-area / suspicious** alerts. Read the message aloud: *"Person remained in restricted zone 'Restricted – Garage' for 10 seconds"*, *"entered … 2 times in …"*. Then **Events page** → point at "Why this was flagged". | "I don't claim the system understands behaviour. It applies clear rules I configured: zone intrusion, loitering, repeated entry, security hours. Every alert says which rule fired and why." Open the zones dialog briefly to show the loitering/repeat settings. | Suspicious-activity detection · explainability · event history |
| **2:35** | **Night Camera** tile (NIGHT MODE badge) → Recordings → play a night clip. | "Night mode is detected from brightness and colour. Person detection still works, using a contrast-enhanced copy — but I'm careful to say enhancement can't create information that isn't there, so night accuracy is lower. Recordings stay untouched." | Night surveillance · honesty about limits |
| **3:05** | Open a **private/incognito window** on `/dashboard` → it redirects to the login page; the homepage is public but shows no camera data. Back in the main window → **Users** page → mention admin / viewer. Optionally show a terminal with `python -m tests.test_system` result. | "Nothing is visible without logging in — not even the streams. For remote use I would not open a port to the internet; I'd use a VPN or an HTTPS reverse proxy, and `REMOTE_MODE` refuses to start if the setup is unsafe. All 143 end-to-end checks pass." | Authentication · remote architecture · testing |
| **3:40** | Back to the Dashboard. | "Summary: motion → YOLO → faces → rules → alerts, all local, explainable, tested. Limits: statistical face recognition, weaker night detection, rule-based activity detection. Future work: pose-based fall detection, push notifications, retention policy." | Conclusion |

**Optional 20-second extra** (if time allows): Cameras → add a camera with a fake RTSP address
(`rtsp://127.0.0.1:9/x`). It shows **Offline**, the other cameras are unaffected, and a *Camera offline*
alert appears after ~20 seconds. Disable it afterwards and the alert resolves itself.

---

## C. If something goes wrong

| Problem during the demo | What to do |
|---|---|
| Webcam tile is *Offline* | Skip step 0:25; say "webcam permission"; continue with the video cameras — everything else is independent. |
| No unknown-person alert yet | The videos loop every ~20 s; wait one loop, or open the Alerts page and show earlier alerts. |
| Nothing new is happening | Videos only trigger events when the scene changes (every loop). Show history in Events / Recordings. |
| Page won't load | Check the backend terminal is running; refresh; log in again. |
| Forgot the admin password | `python scripts/manage_users.py set-password admin` |
| Questions about accuracy | Use the honest answers in [VIVA.md](VIVA.md): statistical, tuned thresholds, "not sure" category, night limits. |

## D. After the demo

Disable or delete the demo video cameras (they create events forever), and stop both servers with Ctrl+C
(any recording in progress is finalized safely).

---

## E. Testing every rule with only your MacBook webcam and your phone

You do not need CCTV cameras or a crowd of volunteers. There are three layers; use as many as you like.

### E1. Staged clips (repeatable, no camera involved)

`python scripts/make_demo_videos.py` makes six short clips. In every one the restricted zone is the **right half** of the
picture. Add each as *Cameras → Add camera → Video file (loops)*, draw the zone, and watch.

**Draw the zone** (Cameras → the octagon **(!)** button → click four corners): top-middle, top-right, bottom-right,
bottom-middle of the picture, i.e. x from 50 % to 100 %. The picture in the editor is shown uncropped, so what you click is
what the detector uses.

| Clip | Rules to set | What should happen |
|---|---|---|
| `demo_empty.mp4` | any | **Nothing.** No event, no alert, count 0 (a negative test) |
| `demo_zone_entry.mp4` | zone, loitering off | One *Restricted area* alert as the person crosses the middle (~10 s in), none while they stay, none when they leave |
| `demo_zone_loiter.mp4` | zone, loitering after 10 s | The intrusion, then one *Loitering* alert about 10 s later; set 60 s and there is **no** loitering alert (negative) |
| `demo_crowd.mp4` | *Alert when at least 3 people stay for 8 s* | The tile counts up to 4; a *Crowd* alert after the third person has been there 8 s. With a limit of 5 there is **no** alert (only 4 people) |
| `demo_repeated.mp4` | zone, repeated entry 3 within 5 min | One intrusion (the 120 s cooldown hides the next two), then *Repeated entry* on the third visit (~49 s) |
| `demo_lowlight_zone.mp4` | zone | The same single intrusion with the **NIGHT MODE** badge |

All of this is also automated: `python -m tests.test_demo_clips` plays the six clips through the real pipeline and detector in about 40 seconds,
including the negative cases. To repeat a demo faster, put `ACTIVITY__ZONE_ALERT_COOLDOWN_SECONDS=20` in `backend/.env`.

*Honest scope:* the people are cut-outs on a plain room. This proves the rules work on real detector output for those scenes, not that they
work in your hallway.

### E2. Your MacBook webcam

1. **Cameras → Add camera → Local webcam, source `0`.** The backend log prints `Camera <id> delivers 1280x720 at 30 fps`.
   A frame rate near 15 means the room is dark.
2. **Restricted zone, loitering, repeated entry.** Sit back so the camera sees you from the head down to as low as it can; the system uses the
   bottom-centre of your detected box as your position. Draw the zone over the lower part of the picture on one side. Step so that spot is inside
   the zone: an alert after about a second. Stay inside for the loitering time: a loitering alert. Step out for **at least 4 seconds** and back in:
   a second entry, and *Repeated entry* when you reach the limit. Another intrusion alert needs the cooldown (120 s) to pass.
3. **Security hours.** In the same dialog set a window that contains the current time, then walk into view: an *after hours* alert (once per 5 min).
4. **Crowd, with only one person.** Play `demo_crowd.mp4` full screen on your phone or a second display and hold it so the webcam sees the people
   (they must appear a fair size: roughly a quarter of the frame height or more). Set *at least 3 people for 8 s*. Expect a count of 3 or 4 once glare and
   moiré stop interfering; if it reads lower, move closer. You can also stand next to the screen to make it 5.
5. **Night.** Switch the lights off or hang a cloth over part of the room until the picture is dark. Below a brightness of about 55 the tile shows
   **NIGHT MODE** and recordings stay untouched. Detection survives moderate darkness; in near-black footage nothing helps (see the README's night table).
6. **Camera offline.** Unplug a USB camera, or add a second camera with a source that cannot open (`rtsp://127.0.0.1:9/x`): *Camera offline* after 20 s,
   resolved automatically when it returns.
7. **Faces:** see *Checking alerts yourself* in the README. A face is only called unknown when it is at least 48 px wide, bright enough and facing the camera.

### E3. Your phone

Two ways, both only partly tested here (there was no phone in the test environment):

* **As a webcam.** Continuity Camera (iPhone with a recent macOS), Camo or DroidCam show up as another webcam. Add it as *Local webcam* with source `1` (or `2`):
  that is how the existing "Mobile" camera was set up. Use landscape, at eye level, within about 2.5 m.
* **As a network camera.** Apps that serve a camera as MJPEG over HTTP (for example IP Webcam on Android) give an address like `http://<phone-ip>:8080/video`:
  add it as *HTTP / MJPEG*. The server tests the same code path against a local MJPEG stream (connect, stream, drop, reconnect), but no specific phone app was tested.

With both the webcam and the phone added you can test two cameras at once, each with its own zones and limits.

### E4. What not to do, and what to expect

* **Do not stage a fall** to test the fall-like rule. It is off by default, looks only at the shape of a person's box, was tested only with scripted boxes, and every alert
  asks a person to review the recording. It is not a safety device.
* A crowd count is **"at least N"**: overlapping or hidden people are missed.
