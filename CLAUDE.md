# CLAUDE.md: project memory for Smart AI-Based Home CCTV Surveillance System

3rd-year college project (Python/FastAPI/OpenCV/YOLOv8 backend, React/Vite/Tailwind frontend, Apple-Silicon Mac).
**Read this file first on every task. Update it at the end of every task** (see "How to keep this file current").
README.md is the user-facing manual; this file is what *I* need to work on the code without re-deriving things.

---

## 1. How to work in this repo (agreements with the user)

* The user **commits themselves**. Never commit/push unless asked. Leave changes in the working tree and say so.
* **No unnecessary features.** Prioritise stability and a working demo. When something is a design choice with a trade-off (e.g. loosening a safety threshold), explain it and let the user decide.
* **Report honestly:** say what was tested, what was not, and what cannot be tested here (see section 8). Never claim a test passed without running it. Quote real numbers.
* **Measure before fixing.** The video-lag and unknown-alert problems were both diagnosed from data (DB rows, timing harness), not guesses. Keep doing that.
* Prefer editing existing code in the existing style (comment density, naming). Docs must be updated with code: README, and `docs/` (PRESENTATION, VIVA, DEMO) when behaviour or test counts change.
* Final reports list: files changed, commands, URLs, test/build results, remaining issues.

## 2. Run, build, test

All backend commands run from `backend/`. `python` is NOT on PATH: use `venv/bin/python`.

```bash
# backend (no --reload for demos)
cd backend && source venv/bin/activate && uvicorn app.main:app --port 8000
# frontend (dev, proxies /api to 127.0.0.1:8000, see frontend/vite.config.js)
cd frontend && npm run dev          # http://localhost:5173
# one-origin mode: npm run build, then SECURITY__SERVE_FRONTEND=true uvicorn ... , open http://127.0.0.1:8000
# frontend gate
cd frontend && npm run lint && npm run build        # oxlint, must stay clean
```

Tests (from `backend/`, use `PYTHONPATH=. venv/bin/python -m tests.<name>`):

| Test | Proves | Time | Last result |
|---|---|---|---|
| `tests.test_system` | Real server on a temp DB/port; auth, roles, cameras, YOLO/recording, night, faces, suspicious rules, alerts/WebSocket, dashboard, restart, network camera, crowd + monitoring status + rule validation, **private data never in the server log** | ~2.5 min | **143/143** |
| `tests.test_face_alerts` | Unknown-person path: confirmations (3; 5 at night), uncertain never alerts, nobody registered, unknown next to known, cooldown, gates report measured values, alert + observation explain themselves, real pipeline -> stored alert | s | **10/10** |
| `tests.test_stream_latency` | Live picture stays current/smooth while a slow AI runs (queueing fake camera); detection still works; unplug → offline → recover | ~40 s | 3/3 (4 repeat runs, stable) |
| `tests.test_activity_rules` | Each suspicious rule, positive+negative, fake clock; camera interruption, tracker loss, real 120 s cooldown | s | **21/21** |
| `tests.test_crowd` | Duplicate-box merging, count in a zone, "at least" flag (any group >= 2), over-limit timer, episodes, cooldown, interruption, median smoothing, **detector input size only on crowd cameras** | s | **17/17** |
| `tests.test_fire_smoke` | Fire/smoke: confirmation rules (fake clock), per-class thresholds + classes by name + refusal of a model without both classes + missing weights = feature off (mocked YOLO), stored alert (camera, time, confidence, type, severity, 0600 snapshot, clip, event upgrade, Events-page reason) through the real pipeline, cooldown, throttle (1 pass/s), slow/failing model never blocks `render()`/the pipeline, overlay never touches the raw frame; 3 real-model negatives (needs `models/fire_smoke_yolov8n.pt` + clips, else SKIP) | s | **25/25** |
| `tests.test_security_hardening` | Mistyped password in the username box never logged; gigapixel photo refused before decoding; stored paths cannot leave storage (symlinks too); world-readable `.env` warned about | s | **4/4** |
| `tests.test_demo_clips` | The six staged clips through the real pipeline + real YOLO (positive and negative; needs `make_demo_videos.py`), **incl. a second pass whose visit starts inside the cooldown** | ~50 s | **7/7** |
| `tests.test_night` | Lighting classification/hysteresis/smoothing, enhancer, and `night_benchmark` properties (real YOLO) | ~30 s | **6/6** |
| `tests.test_activity_pipeline` | Rules through the real pipeline, fake detector | s | 3/3 |
| `tests.test_route_protection` | Every HTTP/WS route needs login; writes need admin | s | 3/3 (49 method/route combos) |

Demo videos: `venv/bin/python scripts/make_demo_videos.py` -> `backend/sample_videos/` (git-ignored; 4 original clips, 6 staged clips `demo_{empty,zone_entry,zone_loiter,crowd,repeated,lowlight_zone}.mp4`, and `demo_person.jpg`). Measurements (all reproducible, none need a camera): `scripts/night_benchmark.py` (~20 s), `scripts/crowd_benchmark.py` (~20 s, known counts), `scripts/perf_benchmark.py` (~5 min: AI cost per stage, live picture under load, alert latency), `scripts/soak_test.py --seconds N` (real server + 6 staged cameras + 1 unreachable RTSP; duplicates, WebSocket delivery, evidence, viewer limits, credential leaks, CPU/memory per minute). Users: `scripts/manage_users.py set-password admin`.

## 3. Architecture and code map

```
Browser (React) --REST + MJPEG + WebSocket (cookie session)--> FastAPI --> CameraManager
CameraManager: per camera = CameraWorker with 2 threads (capture + analysis)
  capture:  camera.read -> publish raw frame -> pipeline.render (overlays) -> JPEG   (never sleeps, never runs a model)
  analysis: newest frame, <= capture_fps/s -> pipeline.analyze:
            lighting -> MOG2 motion -> recording writer -> every 5th frame YOLOv8n -> YuNet/SFace faces
            -> ActivityMonitor rules -> raise_alert() -> DB + AlertBus(WebSocket) + email
```

Backend (`backend/app/`):

| Path | What / how |
|---|---|
| `main.py` | App factory, middleware order (TrustedHost, SecurityHeaders, CORS, OriginCheck/CSRF), lifespan start-up (init_db, ensure_admin, recover_stale_events, load models, start cameras). Camera-permission warm-up must run on the main thread (macOS). |
| `core/config.py` | Pydantic settings; env nesting `A__B`; `.env` in `backend/`. Documented in `.env.example`. |
| `db/models.py`, `db/session.py` | 11 SQLite tables. Auto-migration via `_ADDED_COLUMNS` (add a column there when adding one to a model). No FK from events to cameras (deleting a camera keeps history). |
| `security/` | scrypt passwords, HttpOnly SameSite=Strict session cookie (no max-age, no "remember me"), login throttling, `current_user`/`require_admin`, OriginCheckMiddleware. REMOTE_MODE refuses to start unless safe. |
| `api/*.py` | auth, cameras (+ `/test`, stream, snapshot), events, alerts, people, zones, rules, dashboard, notifications, sources, realtime (WebSocket), health. `_for_user()` masks RTSP source/password for non-admins. |
| `services/camera/` | `manager.py` (CameraWorker, CameraManager), `factory.py` (webcam/rtsp/http/file -> OpenCVCamera; webcam asks for `webcam_width x webcam_height @ webcam_fps`), `opencv_camera.py` (logs the mode the camera really delivers). Files are paced at `capture_fps`; live sources are paced by the camera itself. |
| `services/recording/` | `pipeline.py` (MotionEventPipeline: `analyze()` heavy, `render()` cheap, `process()` = both for tests), `writer.py` (H.264 `avc1` MP4), `recovery.py` (marks stale "recording" events interrupted at start-up), `paths.py`, `event_types.py` (type upgrade order). |
| `services/detection/detector.py` | One shared YOLOv8n (person class, imgsz 320, MPS if available) behind `INFERENCE_LOCK`; `detect(frame, confidence, imgsz)`. A camera with a crowd limit passes `imgsz=DETECTION__CROWD_IMGSZ` (640). |
| `services/detection/fire.py` | `FireSmokeDetector` (second shared YOLOv8n, `models/fire_smoke_yolov8n.pt`, same `INFERENCE_LOCK`): class ids read from the model's `names` (must contain `fire` and `smoke`, else refused), per-class confidence filter; `load_fire_detector()` returns None if disabled / weights missing (never downloads). |
| `services/faces/` | `service.py` (YuNet detect + SFace embed, gallery, `_classify` quality gates; every `FaceResult` carries a short `reason` and a `detail` with the measured value vs limit), `tracker.py` (observations incl. stored `reason`, unknown confirmation, alert cooldown, alert `details.explanation`, overlay drawing), `storage.py`, `runtime.py`. |
| `services/activity/` | `monitor.py` (zones, loitering, repeated entry, security hours, **crowd**, fall-like; `interrupt()` on camera loss; `status()` for the tile), `crowd.py` (`unique_people` duplicate-box merge, `count_people`, `CrowdTimer`), `posture.py`, `rules.py` (per-camera `RulesSpec`: hours, fall, crowd limit/seconds/zone), `zones.py`, `fire.py` (`FireMonitor`: pure confirmation/cooldown rules with an injected clock + `alert()` -> `raise_alert`). Rules use explicit facts and write an explanation into alert `details`. |
| `services/night/lighting.py` | Brightness/colour-spread day/night/IR classification with hysteresis; gamma+CLAHE enhancer (one instance per thread: CLAHE is not thread-safe). |
| `services/alerts.py`, `alert_bus.py`, `notifications/` | `raise_alert()` is the single door for alerts (dedupe keys, severity, snapshot, WebSocket, email channel). |

Frontend (`frontend/src/`): `App.jsx` routes: `/` landing, `/login`, then guarded `RequireAuth` layout with `/dashboard /cameras /alerts /events /recordings /people` and admin-only `/users`; `*` -> NotFound. `hooks/` AuthProvider (`/api/auth/me` on load), AlertsProvider (WebSocket + polling fallback), `usePolling`, `useSignOut`. `components/landing/*` public page, `components/layout/AppLayout.jsx` shell, `CameraTile.jsx` (live MJPEG for first 4 online cameras, 1 fps snapshots beyond that), `ZonesModal.jsx` (zones, security hours, crowd limit, fall switch; shows the picture at its own aspect ratio so clicks equal frame fractions), `MonitoringStrip.jsx` (zones/hours/crowd/fall chips under each tile), `ui/` shared pieces. No external fonts/CDNs (CSP). Tailwind v4 (`@theme` in `index.css`).

## 4. Invariants: do not break these

* **Live picture never waits for the AI.** Do not put models, DB writes or sleeps in `CameraWorker._run` (capture). Heavy work belongs in `pipeline.analyze()` on the analysis thread. `_analysis_lock` guards analysis vs `pipeline.close()`; the offline path sets status OFFLINE *before* taking the lock.
* **Overlapping duplicate boxes are merged right after every YOLO pass** (`unique_people`, in `pipeline._detect_people`) and the night raw/enhanced comparison uses the merged lists; without it a second box round one person "found more people" and inflated counts. Camera loss must call `ActivityMonitor.interrupt()` (done by `pipeline.close()`): no zone/crowd/dwell timer may run across an outage.
* **A crowd count is a lower bound.** Always worded "at least N" (tile shows `N+` for any group of 2 or more); shown as the median of the last 5 cycles; never call it exact. A camera with a crowd limit runs YOLO at 640 px because at 320 packed people are lost (measured: 8 people -> 4.0 on average, 8.0 at 640).
* **The motion cooldown must never hide a person.** `pipeline._person_during_cooldown` keeps looking (every 5th frame, only while something moves) and ends the cooldown when a person is found; otherwise a person who arrives during the cooldown and then stands still is never analysed (found by the soak test; `test_demo_clips` regression).
* **Fire/smoke runs on the analysis thread only, on its own clock** (`pipeline._check_fire`: at most one model pass per `FIRE__INTERVAL_SECONDS`, before the recording branch so it works in a still room), never on capture; failures are contained and rate-limit logged. Fire and smoke are judged separately; one frame never alerts (3 fire / 5 smoke in 8 s); one alert per episode + cooldown (a confirmation inside the cooldown is held back, not lost); `interrupt()` on camera loss. Do not lower the smoke defaults without footage: the model false-fires on soft grey backgrounds (`test_fire_smoke` keeps `demo_entrance.mp4` quiet). Both torch models share `INFERENCE_LOCK` (no concurrent MPS use).
* **Never log what was typed into the username box for an unknown account**, or any camera source/password. `test_security_hardening` and the system test's log canaries enforce it.
* **Recordings are raw, overlays only on the live copy.** `render()` never mutates the frame it is given.
* **Never alert from one frame.** Unknown person needs `FACE__UNKNOWN_CONFIRMATIONS` (3; 5 at night) sightings in one recording, 60 s cooldown per camera. "Unknown" requires a face that is >= 48 px, bright >= 40, yaw <= 0.4, similarity < 0.25; otherwise label is "uncertain" with a `reason` (shown on tile, overlay, log). Do not loosen these silently.
* **Every decision explains itself.** A "not sure" face stores why (`face_observations.reason`, e.g. `too dark to judge: brightness 31 (needs 40)`); an unknown-person alert carries `details` (`rule`, `confirmations`, `similarity`, `explanation`). Keep this when touching `_classify` or `tracker`.
* **All alerts go through `raise_alert()`.** A new suspicious-activity rule reuses an existing `alert_type` and adds a `details.rule` name via `ActivityMonitor._raise(...)` (with facts, `confidence`, `confidence_note`); a genuinely new type must be added to `ALERT_TYPES` in `services/alerts.py`, `ALERT_TYPES` in `frontend/src/utils/meta.js`, `TYPE_TITLES` in `notifications/email.py`, and (if it should upgrade an event) `EVENT_TYPE_RANK` in `recording/event_types.py`. `fire` and `smoke` are such types (alert type = kind; `details.rule` = kind).
* **Every route needs login** (`test_route_protection` enforces it). Writes need admin. No passwords/tokens in localStorage, none hard-coded.
* **A bad camera must never affect others** (isolated threads, exceptions caught per camera).
* Camera source is shown to viewers masked only (`source_display`).

## 5. Feature status: what exists and how it was implemented

| Feature | How | Verified by |
|---|---|---|
| Multi-camera live view | Worker per camera, MJPEG `multipart/x-mixed-replace` from latest JPEG, 10 ms poll | system test |
| Motion + recording | MOG2 (+lighting-jump reset, warm-up 30 frames), H.264 clip, 5 s post-motion, 30 s cap, crash recovery | system test |
| Person detection | YOLOv8n every 5th frame only while recording; confidence 0.5 | system + pipeline tests |
| Face recognition | YuNet + SFace, thresholds known 0.40 / unknown 0.25, "not sure" class | system test (faces) |
| Night / IR | Lighting analyser, raw+enhanced detection keep-the-better, motion denoise | system test (night) |
| Suspicious activity | Zone intrusion, loitering, repeated entry (severity +1), security hours, fall-like (experimental, off) | rules + pipeline + system tests |
| Alerts | 4 types: `unknown_person`, `restricted_area`, `suspicious_activity`, `camera_offline` (auto-resolves). The rule name is in `details.rule`: `zone_intrusion` -> restricted_area; `loitering`, `repeated_entry`, `after_hours`, `fall_like`, `lingering` -> suspicious_activity. Severity low/medium/high/critical. WebSocket + poll fallback; optional email | system test |
| Auth / roles | Cookie session, admin vs viewer, throttling | system + route tests |
| Landing / login / dashboard UI | See section 3; return-to-page after login; sign-out lands on `/` | browser walkthrough, lint+build |
| Video smoothness | Two-thread worker (see section 3) + 720p webcam request | latency harness, `test_stream_latency` |
| Crowd counting | `crowd.py` merge + median of 5 cycles; per-camera `CameraRules.crowd_threshold/seconds/zone_id`; alert = `suspicious_activity` / `details.rule=crowd` (one per episode, 300 s cooldown); tile chip + `MonitoringStrip`; `runtime_info()['monitoring']` | `test_crowd`, `test_demo_clips`, system test, browser |
| Night benchmark | `scripts/night_benchmark.py`; enhancement helps where raw fails (6 %: 85->97 %; heavy noise 37->65 %), useless near black; 0 false positives in an empty dark room | `test_night` |
| Staged demo clips | `make_demo_videos.py`: cut-out people (GrabCut of the one clean full-body person in `bus.jpg`, 4 variants) on the empty room | `test_demo_clips` |
| Reliability / security audit | Soak (20 min, 7 cameras, 160 alerts: 0 duplicates, 0 false alerts, 0 log errors, memory flat, WS 0 of 160 missing, viewer refused 11/11); log canaries; upload pixel cap; path guard; `.env` permission warning | `scripts/soak_test.py`, `test_security_hardening`, system test |
| Fire and smoke | `detection/fire.py` model + `activity/fire.py` rules; alert types `fire` (critical) / `smoke` (high) via `raise_alert()`; snapshot with boxes, event upgraded (rank smoke 5, fire 6), a clip is started if nothing was recording; live box overlay, tile chip (`POSSIBLE FIRE 1/3` -> `FIRE`), `monitoring.fire` status, strip chip, Alerts/Events/Recordings filters | `test_fire_smoke` (mocked model + 3 real-model negatives), system test (+3), scripted-detection browser walkthrough, `scripts/fire_check.py`. **Never run on real fire/smoke** |
| Network camera path | HTTP-MJPEG stand-in served by the test; connect/stream/drop/reconnect | system test (8 checks) |

Measured video smoothness (simulated 30 fps camera, real YOLO+faces, person walking): before 17.6 fps / picture age p95 100 ms (max 223); queueing driver **1,345 ms**; 1080p 16 fps / p95 128 ms. After: **30 fps, p95 8-11 ms** in all cases; YOLO 118 vs 117 runs (no loss of detection).

## 6. Environment gotchas (these have each cost time before)

* **Never run scripts against the real DB** `backend/data/cctv.db` (the user's data; contains their registered person and events). For any script/test set `DATABASE_URL=sqlite:///<tmp>/x.db` and `STORAGE_DIR=<tmp>/storage` *before* importing `app`. Read the real DB only with `sqlite3 -readonly`, and never print `.env` secrets or camera `source` columns (RTSP URLs can hold passwords).
* Real DB cameras: `cam1` "Local Webcam" (webcam 0) and `mobile-32db` "Mobile" (a second webcam device, likely a phone/Continuity camera); both disabled when last looked. Other project of the user holds port 8000 sometimes (Mumbai House Price Predictor): check with `lsof -iTCP:8000 -sTCP:LISTEN -n -P`; do not kill processes I did not start.
* This session cannot open the webcam (macOS camera permission belongs to the launching app). Hardware behaviour can only be simulated.
* zsh: quote globs (`--include='*.py'`); to word-split a string variable use `${=var}` and never backslash-escape it; macOS `sed -i ''`; no `timeout`; foreground `sleep` is blocked (use a background until-loop); `print` to a pipe needs `flush=True` before `os._exit`.
* Throwaway checks: use a `git worktree` under the scratchpad and remove it afterwards (`git worktree remove --force` + `prune`).
* Built-in browser: screenshots lag one capture (take two); call `resize_window` to emulate widths and **reset with preset "desktop"** afterwards; coordinate clicks need a fresh screenshot; `form_input` does not trigger React state (type with the keyboard instead); a reload inside a script cuts it off. Start throwaway servers with a temp DB and a test admin password, then stop them.
* `httpx` is NOT installed, so `fastapi.testclient` cannot be used (call handlers directly with a Starlette `Request`, as `test_security_hardening` does). `timeout` does not exist on this Mac. A foreground command is capped at 10 minutes: poll a log file in a loop of at most ~550 s. Long benchmarks must run alone (the machine is an 8-core, 8 GB M3): do not start other heavy work while measuring. The built-in browser's accessibility tree can come back empty: use screenshots + keyboard (click a field, type, Tab, Return).
* Frontend must not load external fonts/scripts (CSP). `-webkit-` fallbacks already exist for Safari.
* Test-only env in the system test: `SEED_DEFAULT_CAMERA=false`, `ALERTS__CAMERA_OFFLINE_GRACE_SECONDS=5`, `FACE__ENROLL_MAX_YAW_RATIO=1.0`. Do not put those in real config.

## 7. Settings worth knowing (full list in `backend/.env.example`)

`WEBCAM_WIDTH/HEIGHT/FPS` (1280/720/30; 0 = camera default) · `CAPTURE_FPS` (20: AI rate and video-file playback; does not limit the live picture) · `MOTION__*` · `DETECTION__RUN_EVERY_N_FRAMES` (5) · `FACE__KNOWN_THRESHOLD/UNKNOWN_THRESHOLD/MIN_FACE_PX/MIN_FACE_BRIGHTNESS/MAX_YAW_RATIO/UNKNOWN_CONFIRMATIONS/ALERT_COOLDOWN_SECONDS` · `NIGHT__*` · `ACTIVITY__*` (incl. `ZONE_ALERT_COOLDOWN_SECONDS` 120, `CROWD_SEVERITY/GRACE_SECONDS/ALERT_COOLDOWN_SECONDS`) · `FIRE__*` (`ENABLED`, `MODEL_PATH`, `FIRE_/SMOKE_CONFIDENCE` 0.50/0.60, `FIRE_/SMOKE_CONFIRM_HITS` 3/5, `CONFIRM_WINDOW_SECONDS` 8, `CLEAR_SECONDS` 10, `FIRE_/SMOKE_ALERT_COOLDOWN_SECONDS` 120/180, `INTERVAL_SECONDS` 1.0) · `ALERTS__CAMERA_OFFLINE_GRACE_SECONDS` (20) · `EMAIL__*` · `REMOTE_MODE`, `ALLOWED_HOSTS`, `CORS_ORIGINS`, `SECRET_KEY`, `SECURITY__SERVE_FRONTEND`. Zone limits and security hours live in the DB, edited from the dashboard.

## 8. Tested vs not tested (be explicit about this in reports)

* **Verified only on simulated footage (needs the user's real cameras):** face recognition on their cameras, night mode on a real low-light camera, **infrared hardware (never tested; the infrared row is a synthetic monochrome clip)**, a phone as a camera (Continuity/Camo/IP-webcam apps untested), zone accuracy for a real person at a real angle. Staged clips are cut-outs on a plain room.
* **Fire/smoke: never seen real fire or smoke.** Alert path = mocked model output (+ a browser walkthrough with scripted detections); the real model was only run on footage with NO fire (0 detections on 9 of 10 clips, 15 false "smoke" on the blurry `demo_entrance.mp4`). Recall, real-world confidence values and false-alarm rate on the user's cameras are unknown; thresholds are cautious guesses.
* **Not testable here:** a real webcam or RTSP/IP camera (simulated with a fake camera and an HTTP-MJPEG server); Safari and Firefox (only the Chromium-based built-in browser; Tailwind v4 minimums Safari 16.4 / Chrome 111 / Firefox 128 are documented). Playwright WebKit/Firefox would need a ~150 MB download, which requires the user's OK.
* Tested: desktop, tablet (768 and 1024 px, every page, no horizontal scroll) and phone widths; macOS Apple Silicon only.
* The landing-page preview is illustrative, labelled "Sample data"; the dashboard shows only real API data.

## 9. Open items / user decisions pending

* **Unknown-person alerts not firing on the user's cameras (still open).** Re-verified 2026-10-30 on the real DB (read-only): 7 face observations (1 known, 6 uncertain, 0 unknown), **0 alerts, 0 zones, 0 camera rules**. The alert chain is proven correct by `test_face_alerts` and the system test, so the faces on their cameras never pass the quality gates (their tests ran ~01:45-02:00 local, likely a dim room; phone-camera faces had detector score 0.80-0.86 and similarity 0.06-0.09). The *reason* was not stored for those old rows; **new sightings now record it** (Events page *Face not judged*, tile chip, server log, `face_observations.reason`). Next step: user runs the manual checks in README "Checking alerts yourself" and reports the reason. Options if gates keep holding good-looking faces: fix the setup, loosen one `FACE__*` setting (more false alarms), or add a lower-severity "unrecognised person" alert (**not built; only if asked**).
* The user has **no zones or camera rules configured**, so zone/loitering/repeated-entry/after-hours alerts cannot fire until they set them in Cameras -> (!) Zones & security rules (by design).
* Changes since the last commit are **uncommitted** (see change log). The user commits.
* **Measured but not proven:** 20-minute memory is flat (729-1,011 MB per-minute medians) but days of uptime were not tested (`soak_test.py --seconds 3600` overnight). WebSocket delivery lost 0 of 160 in the last run; an earlier 10-minute run reported 2 of 80 missing before the check was changed to count only alerts after the client connected, and that was not proven to be the cause (the dashboard also polls every 15 s). No dependency vulnerability scan was run.
* `backend/.env` is mode 644 on the user's machine (the app now warns at start-up); the user must run `chmod 600 backend/.env`. I did not change their file.
* **Pose-based fall detection is NOT built.** The user asked for it "if practical": no pose weights exist locally (only unrelated YAML configs) and `yolov8n-pose.pt` (~6 MB) would be a download, so it was not done without OK, and untestable code was not shipped. Ask before downloading; if approved, add it as an optional, off-by-default module behind the same human-review warning, with a pure keypoints->fall function tested on synthetic keypoints.
* **Fire/smoke thresholds are uncalibrated** (fire 0.50, smoke 0.60 chosen to silence the one false alarm found). Next step: the user tries `scripts/fire_check.py` on a fire/smoke video and the webcam walkthrough in README "Fire and smoke detection", then reports confidences; tune `FIRE__*_CONFIDENCE`. Model licence is AGPL-3.0 per the model card; the D-Fire dataset's licence was NOT verified. The weights file is git-ignored: a fresh clone needs the `curl` in the README or the feature is off (logged). No per-camera fire switch (global `FIRE__ENABLED` only); a fire burning past its cooldown does not re-alert.
* Fall-like (box ratio) stays experimental/off by default; only scripted boxes were tested.
* Not built (listed as future work in README): retention policy, push notifications, WebRTC/HLS, Docker, persistent-identity tracking, dense-crowd density estimation.

## 10. Change log (newest first; add an entry after every task)

**2026-10-31: AI fire and smoke detection**
* **Before building:** re-ran the alert suites on the untouched code (face alerts 10, rules 21, pipeline 3, hardening 4: all pass) and re-read the real DB read-only (0 alerts, 20 events, 7 face observations): the alert delivery chain is sound; the open unknown-person item is still the face-quality gates on the user's cameras and was **not changed** by this task.
* **Model:** `rabahdev/fire-smoke-yolov8n` `best.pt` (YOLOv8n fine-tuned on D-Fire, 640 px, classes `0 smoke / 1 fire`, 6.23 MB, SHA-256 `b9163379...4f28f`, **AGPL-3.0** per its card; D-Fire's own licence NOT checked; card's mAP50 0.754 not reproduced). Downloaded with the user's OK to `backend/models/fire_smoke_yolov8n.pt` (git-ignored); loads in Ultralytics 8.3.55. Nothing auto-downloads: missing file = feature off + one log line.
* **How:** `services/detection/fire.py` (shared detector, classes by name), `services/activity/fire.py` (`FireMonitor`: separate fire/smoke, 3/5 detections in 8 s, one alert per episode, held-back-not-lost cooldown, `interrupt()`), `pipeline._check_fire` (analysis thread, one pass per second, before the recording branch, starts a clip as evidence, keeps recording while an episode is active), live overlay + `monitoring.fire` status, `INFERENCE_LOCK` shared with the person detector. New alert types `fire` (critical) / `smoke` (high); event ranks smoke 5, fire 6. Frontend: meta, icons, tile chip (`POSSIBLE FIRE n/3` -> `FIRE`), strip chip, Alerts "Why" says "model confidence" (it said "person detection"), Events/Recordings filters, Events-page reason (`RULE_ALERT_TYPES`). `scripts/fire_check.py` tries the model on any file; `perf_benchmark.py` gained fire rows (and now counts every published frame: a box drawn over its frame-number stamp had made it undercount).
* **Findings (real model, footage without fire):** 0 detections on 9 of 10 clips + the photo, but **15 false "smoke" detections (0.51-0.74) on `demo_entrance.mp4`** (blurred grey TV background); the first-draft thresholds (smoke 0.50, 5/8 s) raised a false alert on it, so defaults became fire 0.50 / smoke 0.60 (regression-tested). **Recall unknown** (no fire footage). Defect found by its own test: an episode did not end when no empty cycles were fed in (clear check now runs before the new sighting).
* **Measured (M3, simulated camera):** model pass 7.3 ms (p95 7.9) once per camera per second; live fps 29.9-30.0 and p95 picture age 7.5-7.8 ms with and without it (3 alternated runs with faces; CPU 88-90 vs 88 % of a core); capture thread 29.7-30.1 fps.
* **Verified:** `test_fire_smoke` 25/25 (mutation-checked), all older suites re-run and passing (system 143/143 incl. 3 new checks, face alerts 10, rules 21, pipeline 3, crowd 17, hardening 4, route protection 3, night 6, demo clips 7, stream latency 3), frontend lint + build clean, browser walkthrough on a throwaway temp-DB server with SCRIPTED detections (live box, toast, Alerts entry with snapshot/explanation/Recording, tile chip, strip, Events badge). Real DB untouched. **Not verified:** real fire/smoke, real webcam/phone, Safari/Firefox.
* **Docs:** README ("Fire and smoke detection" section with model facts, setup, webcam/phone test steps, measured results, limitations; config rows, tests, troubleshooting, limitations), VIVA (3 Q&As), PRESENTATION/DEMO counts, `.env.example`, this file. Not committed.

**2026-10-30 (night): Final reliability and integration audit**
* **No real camera available** (`cv2.VideoCapture(0/1)` fails in this session), so every camera result is simulation; the report says so. Verified in a real browser (login typed into the form, dashboard, crowd tile `2+ in view / limit 3`, strip, alerts) on a throwaway server.
* **Defects found and fixed (each with a regression test shown to fail without the fix):** (1) **cooldown blind spot**: a person who arrives while the 10 s post-recording cooldown runs and then stands still made no motion, so nothing watched them: soak showed 1 loitering alert where 4 were expected -> `_person_during_cooldown`; (2) failed logins logged the typed username for unknown accounts (people type passwords there) -> not logged; throttle log no longer names it; (3) uploads capped by bytes only: a tiny gigapixel PNG could need GBs -> 40 MP cap checked from the header (`FACE__ENROLL_MAX_IMAGE_PIXELS`); (4) stored paths can now never resolve outside storage (`inside_storage`); (5) `.env` world-readable -> start-up warning; (6) crowd counter lost packed people at 320 px (4 people -> 3.0, 8 -> 4.0 on average) -> 640 px on cameras with a crowd limit (+~6 ms/pass); (7) a bare count of 3 was misleading since overlap hides people -> `N+` for any group of 2+.
* **Measured** (README "Performance, measured", Apple M3): live 28.8-30.0 fps, picture age p95 7.6-9.5 ms (worst frame 41 ms; one earlier run saw 103 ms once) under every load; crowd counting +3 CPU points / +7 ms AI-cycle p95; face recognition +5 points / +35 ms; alert delay 0.6-1.2 s after the earliest legitimate moment; YOLO 10.9-11.6 ms, faces 23 ms, enhancement 6.7 ms, merge+count 0.016 ms. Soak 20 min: 160 alerts, 0 duplicates, 0 false, 0 errors, CPU median 127 % of a core, memory flat. Crowd accuracy on built frames: exact at 640 px for 3/4/6/8 people apart; falls with overlap (8 people at 50 % overlap -> 3.5).
* **New files:** `scripts/{perf_benchmark,crowd_benchmark,soak_test}.py`, `tests/test_security_hardening.py`; `Server` in `tests/test_system.py` takes `extra_env`; system test gained 4 checks (140). Tests now: system 140, rules 21, crowd 17, demo clips 7, night 6, face alerts 10, hardening 4, pipeline 3, route protection 3, latency 3; frontend lint + build clean.
* **Docs:** README (security audit table, performance, crowd accuracy, limitations, tests), `docs/DEMO.md` Part 0 (12-minute faculty checklist with LIVE / STAGED / PRERECORDED / NOT-VERIFIED labels), VIVA (5 Q&As), PRESENTATION (results, limitations, tests), `.env.example`. Not committed.

**2026-10-30 (evening): Make features testable with only a webcam and a phone**
* **Audit** (details in README "What is verified, and how"): A works+verified on staged footage (person detection, motion recording, zone intrusion, loitering, repeated entry, night classification, alerts); B implemented but only simulated (faces on the user's cameras, real night, IR hardware, webcam/RTSP, phone); C experimental (fall-like, lingering); D missing (pose-based fall, persistent-ID tracking, dense-crowd density). There is no face *tracking* across frames: `FaceEventTracker` aggregates sightings; people are matched by nearest box only.
* **Real defects found and fixed (each with a test that fails without the fix):** (1) a camera outage shorter than the 4 s exit gap was silently bridged, so a loiter timer ran across it -> `ActivityMonitor.interrupt()` called from `pipeline.close()`; (2) the night rule "keep the pass that finds more people" preferred a pass that merely drew a second box round one person, and YOLO duplicates would inflate any count -> `unique_people` after every pass; (3) **zone editor stored wrong coordinates on non-16:9 cameras** (picture cropped with `object-cover` in a 16:9 box while clicks were saved as fractions of the box) -> picture now shown at its own aspect ratio; verified in the browser (clicked 10-90 % -> stored 0.099-0.900 -> server drew the outline at 9.8-89.8 %).
* **New:** crowd counting (`activity/crowd.py`, rule in `ActivityMonitor._check_crowd`, `CameraRules.crowd_*` columns + `_ADDED_COLUMNS` migration verified on a copy of the real DB, rules API validation, zone delete clears `crowd_zone_id`); live `monitoring` block in camera status; tile crowd chip + `MonitoringStrip`; crowd/fall controls and warnings in `ZonesModal`; `RULES.crowd`; six staged clips; `scripts/night_benchmark.py`; `tests/test_crowd.py` (16), `test_demo_clips.py` (6), `test_night.py` (6), +5 in `test_activity_rules.py` (21), +10 system checks (136).
* **Measured:** night table in README; with duplicate-merging disabled the crowd clip showed a count of 7 and fired a false 5-people alert, enabled: peak 4, no alert. Re-entry after 3/6/10/16 s gaps was always caught on real footage (the 10 s motion cooldown could in principle hide a very brief visit; not observed).
* Verified: all suites above re-run on the final code, frontend lint + build clean, Alerts/Cameras/Dashboard checked in the browser on a throwaway server. Docs: README (features, config, night + crowd + verification sections, tests, limitations), `docs/DEMO.md` part E (staged clips, MacBook webcam, phone), VIVA (3 Q&As), PRESENTATION, `.env.example`. Not committed.

**2026-10-30 (later): Alert pipeline audit (unknown-person and rule alerts)**
* Traced camera -> capture -> YOLO -> faces -> tracker -> ActivityMonitor -> `raise_alert` -> SQLite -> AlertBus/WebSocket -> React. **No defect in the delivery chain**: 6 of the 10 new tests passed on the unchanged code (confirmations, cooldown, night, nobody registered, known+unknown, unknown face -> stored alert through the real pipeline). Hypothesis "phone feed rotated/mirrored" tested and rejected (mirrored faces classify fine; rotated faces are not detected at all).
* Confirmed gaps (4 tests failed before): the gate that held a face back was never recorded; gates reported no numbers; the unknown-person alert had empty `details` (the rule alerts already explained themselves).
* Fix: `FaceResult.detail` (measured value vs limit) from `_classify`; new nullable `face_observations.reason` (+ `_ADDED_COLUMNS` migration, checked on a *copy* of the real DB: column added, 7 rows intact, integrity ok, real file untouched); tracker logs one observation per distinct reason, logs the detail, and builds unknown-alert `details`; events API `uncertain_reasons`; live status `detail`; Alerts page shows `details.explanation` (new `RULES.unknown_person`); Events page/phone cards/video modal show "Face not judged: ...". Thresholds, cooldowns, confirmations, alert types, auth unchanged.
* Tests: new `tests/test_face_alerts.py` (10); `test_system.py` +2 checks (unknown alert explains itself; `uncertain_reasons` exposed) -> 126/126; rules 16/16, pipeline 3/3, route protection 3/3, stream latency 3/3 re-run and passing; frontend lint + build clean; Alerts and Events pages checked in the browser on a throwaway server with seeded data.
* Docs: README (schema, API, test tables, troubleshooting, new "Checking alerts yourself" manual guide with webcam + phone steps), `docs/VIVA.md` (new Q&A). Files: `backend/app/services/faces/{service,tracker}.py`, `app/db/{models,session}.py`, `app/api/events.py`, `app/services/camera/manager.py`, `tests/test_face_alerts.py`, `tests/test_system.py`, `frontend/src/{utils/meta.js,pages/AlertsPage.jsx,pages/EventsPage.jsx,components/EventBadges.jsx,components/CameraTile.jsx}`.
* Not testable here: the user's real webcam/phone faces, so the actual blocking reason on their cameras is still unknown until they run it.

**2026-10-30: Why unknown persons raise no alerts**
Diagnosed from the real DB (read-only). Added the reason a face is "not sure" to the log line (`tracker._log_observation`), the live overlay text (`draw_faces`) and the dashboard tile chip (`CameraTile.jsx`, `unsureWhy`); README troubleshooting row. Verified each gate with synthetic faces (unknown / too small / turned / dark / known); system test 124/124; lint+build clean. Files: `backend/app/services/faces/tracker.py`, `frontend/src/components/CameraTile.jsx`, `README.md`.

**2026-10-29: Live-video lag, tablet, network camera, landing honesty**
* Root cause: one thread did read+AI+draw and slept between reads (picture froze on every YOLO/face cycle; queueing drivers built a backlog). Fix: `CameraWorker` split into capture + analysis threads; `MotionEventPipeline.process` split into `analyze`/`render` (separate CLAHE enhancer for the view); `STREAM_MAX_FPS=40`; MJPEG poll 30 -> 10 ms; webcam requested at 1280x720@30 (`webcam_*` settings, `.env.example`), real mode logged on open.
* Tests: new `tests/test_stream_latency.py` (fails on the old design: 8.9 fps); `test_system.py` gained the network-camera section (`MjpegServer`, 8 checks; restart test now returns the new client) -> 124/124.
* Frontend: Events table fits at 1024 px (Duration hidden between `lg` and `xl`, tighter padding); landing preview chrome now says "Sample data" (was "System online"); caption contrast.
* Docs: README (architecture, video smoothness section, config, troubleshooting, test table, limitations), VIVA (lag Q&A), PRESENTATION, DEMO updated to 124 checks and two-thread model.
* Verified with: timing harness (real YOLO+faces, fake camera), full suites, browser measurements at 768/1024.

**Landing page + login + dashboard phase (committed)**: premium dark landing page, dedicated login wired to the existing cookie auth, route guards with return-to-page, sign-out to `/`, dashboard UI upgrade on real data, NotFound page, favicon, README/DEMO updates; lint+build clean; `test_route_protection` unchanged.

**Final submission phase (committed)**: clean-setup run, README rewrite, `docs/PRESENTATION.md` (A-P), `docs/VIVA.md`, `docs/DEMO.md`; system test found and fixed a real bug (RTSP password visible to viewers).

**Suspicious-activity module (committed)**: zones (`loiter_seconds`, `repeat_entries`, `repeat_window_seconds`), `CameraRules` (security hours, fall detection), `ActivityMonitor`, `PostureState`, `/api/.../rules`, frontend zone/rules UI, reasons on Alerts/Events pages; `tests/test_activity_rules.py`, `test_activity_pipeline.py`.

**Earlier phases (committed; see `git log`)**: 1 scaffold, 2 camera streaming, 3 motion + recording, 4 YOLO person detection, 5 multi-camera dashboard, 6 face recognition + unknown-person alerts, 7 alerts / night mode / auth / remote-access architecture.

---

## How to keep this file current

At the end of **every** task: (1) add a change-log entry (date, what, how, files, how verified, caveats); (2) update the feature table, settings, invariants or open items if they changed; (3) update test counts in section 2; (4) move resolved items out of section 9; (5) keep it factual: if something was not tested, write that. Keep the file under ~250 lines; link to README for anything long.
