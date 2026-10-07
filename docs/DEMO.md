# ▶️ Live Demo Script (about 4 minutes)

Goal: show that every major feature **works**, in the order a professor will care about. Rehearse it
twice. Everything below was exercised against a clean install.

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

Sign in as `admin` (the password you put in `backend/.env`).

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
| **0:00** | **Dashboard.** Point at the counters and the camera tiles (LIVE / REC badges). | "This is the control room. Four cameras stream live over MJPEG, each in its own thread, so one failure can't stop the others. The badges show live, recording, and people in view." | Live CCTV · multiple cameras · dashboard |
| **0:25** | Walk in front of the **webcam tile**. Point at the box, `person 9x%`, then your **name** in green. | "Motion detection wakes up YOLO, which finds the person; then the face model recognizes me as a registered person. Recording started automatically — see REC." | Motion · YOLO · face recognition · recording |
| **0:55** | Wait for / point at the **Front Entrance** tile: **UNKNOWN** red box, then the bell badge / toast appears. Click it → **Alerts page**. | "The man in this video isn't registered, so he is classified unknown — after 3 confirmations, so one blurry frame can't raise an alarm. Here is the alert: severity, time, snapshot, and a link to the recording." Click **Recording** to play it; click **Resolve**. | Unknown-person detection · alerts · event recording/playback |
| **1:40** | On the Alerts page, open the **restricted-area / suspicious** alerts. Read the message aloud: *"Person remained in restricted zone 'Restricted – Garage' for 10 seconds"*, *"entered … 2 times in …"*. Then **Events page** → point at "Why this was flagged". | "I don't claim the system understands behaviour. It applies clear rules I configured: zone intrusion, loitering, repeated entry, security hours. Every alert says which rule fired and why." Open the zones dialog briefly to show the loitering/repeat settings. | Suspicious-activity detection · explainability · event history |
| **2:35** | **Night Camera** tile (NIGHT MODE badge) → Recordings → play a night clip. | "Night mode is detected from brightness and colour. Person detection still works, using a contrast-enhanced copy — but I'm careful to say enhancement can't create information that isn't there, so night accuracy is lower. Recordings stay untouched." | Night surveillance · honesty about limits |
| **3:05** | Open a **private/incognito window** on the same address → only the login form. Back in the main window → **Users** page → mention admin / viewer. Optionally show a terminal with `python -m tests.test_system` result. | "Nothing is visible without logging in — not even the streams. For remote use I would not open a port to the internet; I'd use a VPN or an HTTPS reverse proxy, and `REMOTE_MODE` refuses to start if the setup is unsafe. All 116 end-to-end checks pass." | Authentication · remote architecture · testing |
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
