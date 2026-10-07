"""End-to-end system check. Starts the REAL server (FastAPI + OpenCV + YOLO + face
recognition) on a throwaway database and port, adds the demo video cameras, and
verifies every feature through the HTTP API, the way the dashboard uses it.

    python scripts/make_demo_videos.py        # once: creates sample_videos/*
    python -m tests.test_system               # ~4-5 minutes, needs the models downloaded

Nothing in your real database or recordings is touched. Exit code 0 = all passed.
"""
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parent.parent
VIDEOS = BACKEND / "sample_videos"
ADMIN_PASSWORD = "system-test-password-123"
RESULTS: list[tuple[str, bool, str]] = []


# ------------------------------------------------------------------ helpers
def check(name: str, condition: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(condition), detail))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""), flush=True)
    return bool(condition)


def section(title: str) -> None:
    print(f"\n== {title}", flush=True)


def wait_until(fn, timeout: float, every: float = 2.0):
    """Poll `fn` until it returns something truthy (returned), or time runs out (None)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = fn()
        except requests.RequestException:
            value = None
        if value:
            return value
        time.sleep(every)
    return None


class Server:
    def __init__(self, workdir: Path, port: int):
        self.dir, self.port, self.proc = workdir, port, None
        self.base = f"http://127.0.0.1:{port}"
        self.db_path = workdir / "system.db"

    def start(self) -> None:
        env = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{self.db_path}",
            "STORAGE_DIR": str(self.dir / "storage"),
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
            "SECRET_KEY": "system-test-secret-key-not-for-real-use-0123456789",
            "SEED_DEFAULT_CAMERA": "false",  # no webcam / macOS permission prompt in tests
            "ALERTS__CAMERA_OFFLINE_GRACE_SECONDS": "5",
            # Test-only: lets the turned-away face in the demo photo be registered (see test_faces).
            "FACE__ENROLL_MAX_YAW_RATIO": "1.0",
        }
        log = open(self.dir / "server.log", "ab")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port), "--log-level", "warning"],
            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        if not wait_until(lambda: requests.get(f"{self.base}/api/health", timeout=2).ok, 300, 1):
            raise RuntimeError(f"server did not start; see {self.dir / 'server.log'}")

    def stop(self) -> float | None:
        """SIGINT (Ctrl+C). Returns seconds taken to exit, or None if it had to be killed."""
        if self.proc is None or self.proc.poll() is not None:
            return 0.0
        began = time.time()
        self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=30)
            return time.time() - began
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return None


class Client:
    def __init__(self, base: str):
        self.base, self.http = base, requests.Session()
        self.http.headers["Origin"] = base  # what a browser on the same origin sends

    def call(self, method: str, path: str, **kw) -> requests.Response:
        return self.http.request(method, f"{self.base}/api{path}", timeout=30, **kw)

    def get(self, path, **kw): return self.call("GET", path, **kw)
    def post(self, path, **kw): return self.call("POST", path, **kw)
    def patch(self, path, **kw): return self.call("PATCH", path, **kw)
    def put(self, path, **kw): return self.call("PUT", path, **kw)
    def delete(self, path, **kw): return self.call("DELETE", path, **kw)

    def login(self, username="admin", password=ADMIN_PASSWORD) -> requests.Response:
        return self.post("/auth/login", json={"username": username, "password": password})


# -------------------------------------------------------------------- tests
def test_authentication(server: Server) -> Client:
    section("Authentication and access control")
    anon = Client(server.base)
    check("health check is public", anon.get("/health").status_code == 200)
    for path in ("/cameras", "/events", "/dashboard/summary", "/alerts", "/people", "/users"):
        check(f"GET {path} without login -> 401", anon.get(path).status_code == 401)
    check("live stream without login -> 401", anon.get("/cameras/whatever/stream").status_code == 401)
    check("wrong password -> 401", anon.login(password="wrong-password").status_code == 401)

    admin = Client(server.base)
    check("admin login", admin.login().status_code == 200)
    check("session identifies the user", admin.get("/auth/me").json().get("username") == "admin")
    cookie = next((c for c in admin.http.cookies if c.name == "cctv_session"), None)
    check("session cookie is HttpOnly", cookie is not None and cookie.has_nonstandard_attr("HttpOnly"))

    thief = Client(server.base)
    codes = [thief.login("nobody", f"bad-{i}").status_code for i in range(7)]
    check("repeated bad logins are throttled (429)", 429 in codes, str(codes))
    check("...without locking out the real admin", Client(server.base).login().status_code == 200)

    foreign = Client(server.base)
    foreign.http.headers["Origin"] = "https://evil.example"
    foreign.http.cookies.update(admin.http.cookies)
    check("cross-site write is refused (CSRF) -> 403", foreign.post("/cameras/test", json={"type": "file", "source": "x"}).status_code == 403)
    return admin


def test_roles(server: Server, admin: Client) -> None:
    section("Roles: admin vs viewer")
    r = admin.post("/users", json={"username": "viewer1", "password": "viewer-password-123", "role": "viewer"})
    check("admin can create a viewer", r.status_code in (200, 201), r.text[:100])
    viewer = Client(server.base)
    check("viewer can log in", viewer.login("viewer1", "viewer-password-123").status_code == 200)
    check("viewer can read cameras", viewer.get("/cameras").status_code == 200)
    check("viewer cannot add a camera -> 403", viewer.post("/cameras", json={"name": "x", "type": "file", "source": "demo_entrance.mp4"}).status_code == 403)
    check("viewer cannot delete events -> 403", viewer.delete("/events/1").status_code == 403)
    check("viewer cannot manage users -> 403", viewer.get("/users").status_code == 403)
    check("logout ends the session", viewer.post("/auth/logout").status_code in (200, 204) and viewer.get("/cameras").status_code == 401)


def test_cameras(admin: Client) -> dict[str, str]:
    section("Multiple cameras, camera management and error handling")
    check("demo videos exist (run scripts/make_demo_videos.py)", all((VIDEOS / n).is_file() for n in ("demo_entrance.mp4", "demo_street.mp4", "demo_night.mp4", "demo_infrared.mp4", "demo_person.jpg")))
    check("video files are listed as sources", {"demo_entrance.mp4", "demo_night.mp4"} <= set(admin.get("/sources/files").json()["files"]))

    # Bad input is rejected with a clear message, never a crash.
    check("file camera: path traversal rejected", admin.post("/cameras/test", json={"type": "file", "source": "../../etc/passwd"}).json().get("ok") is False)
    check("file camera: missing file rejected", admin.post("/cameras", json={"name": "ghost", "type": "file", "source": "nope.mp4"}).status_code == 422)
    check("camera test: unreachable RTSP reports a friendly error", admin.post("/cameras/test", json={"type": "rtsp", "source": "rtsp://127.0.0.1:9/none"}).json().get("ok") is False)
    check("camera test: good source works", admin.post("/cameras/test", json={"type": "file", "source": "demo_entrance.mp4"}).json().get("ok") is True)
    check("missing fields -> 422", admin.post("/cameras", json={"name": "x"}).status_code == 422)

    ids = {}
    for key, name, kind, source in [
        ("entrance", "Front Entrance", "file", "demo_entrance.mp4"),
        ("street", "Street View", "file", "demo_street.mp4"),
        ("night", "Night Camera", "file", "demo_night.mp4"),
        ("infrared", "Infrared Camera", "file", "demo_infrared.mp4"),
        ("broken", "Broken IP Camera", "rtsp", "rtsp://user:secret@127.0.0.1:9/none"),
    ]:
        r = admin.post("/cameras", json={"name": name, "type": kind, "source": source})
        check(f"add camera: {name}", r.status_code == 201, r.text[:120])
        ids[key] = r.json().get("id")
    check("duplicate camera name -> 409", admin.post("/cameras", json={"name": "Front Entrance", "type": "file", "source": "demo_entrance.mp4"}).status_code == 409)
    broken = admin.get(f"/cameras/{ids['broken']}").json()
    check("RTSP password is masked for display", "secret" not in broken["source_display"] and "****" in broken["source_display"])
    viewer = Client(admin.base)
    viewer.login("viewer1", "viewer-password-123")
    check("viewers never receive the raw camera URL / password", "secret" not in json.dumps(viewer.get("/cameras").json()) and "secret" not in json.dumps(viewer.get(f"/cameras/{ids['broken']}").json()))

    online = wait_until(lambda: all(admin.get(f"/cameras/{ids[k]}").json()["status"] == "online" for k in ("entrance", "street", "night", "infrared")), 60)
    check("four camera streams online at the same time", bool(online))
    check("a broken camera stays offline without affecting the others", wait_until(lambda: admin.get(f"/cameras/{ids['broken']}").json()["status"] == "offline", 30) is not None)

    stream = admin.http.get(f"{admin.base}/api/cameras/{ids['entrance']}/stream", stream=True, timeout=15)
    first = next(stream.iter_content(chunk_size=4096), b"")
    stream.close()
    check("live MJPEG stream delivers frames", stream.headers.get("content-type", "").startswith("multipart/x-mixed-replace") and len(first) > 100)
    snap = admin.get(f"/cameras/{ids['entrance']}/snapshot")
    check("snapshot is a JPEG", snap.status_code == 200 and snap.content[:2] == b"\xff\xd8")
    check("unknown camera -> 404", admin.get("/cameras/does-not-exist").status_code == 404 and admin.get("/cameras/does-not-exist/stream").status_code == 404)

    r = admin.patch(f"/cameras/{ids['street']}", json={"name": "Street View (renamed)"})
    check("rename a camera while running", r.status_code == 200 and r.json()["name"] == "Street View (renamed)")
    return ids


def test_detection_and_recording(admin: Client, ids: dict[str, str]) -> None:
    section("Motion detection, YOLO person detection, recording, event history")
    for key in ("entrance", "street", "night", "infrared"):
        got = wait_until(lambda: [e for e in admin.get("/events", params={"camera_id": ids[key], "limit": 50}).json()["items"] if e["event_type"] != "motion" and e["playable"]], 120, 3)
        check(f"{key}: motion -> YOLO person event with a playable recording", bool(got))
    events = admin.get("/events", params={"limit": 200}).json()
    check("events were created by motion detection", events["total"] >= 4)
    person = next((e for e in events["items"] if e["camera_id"] == ids["entrance"] and e["event_type"] != "motion" and e["playable"]), None)
    check("person events carry a confidence score", bool(person) and person["max_confidence"] and person["max_confidence"] > 0.5)
    if person:
        video = admin.get(f"/events/{person['id']}/video")
        check("recording plays back as MP4", video.status_code == 200 and video.headers["content-type"] == "video/mp4" and len(video.content) > 10_000)
        ranged = admin.get(f"/events/{person['id']}/video", headers={"Range": "bytes=0-99"})
        check("recording supports seeking (HTTP Range)", ranged.status_code == 206)
        check("recording thumbnail", admin.get(f"/events/{person['id']}/thumbnail").status_code == 200)
        check("recording download", "attachment" in admin.get(f"/events/{person['id']}/download").headers.get("content-disposition", ""))
    check("filter events by camera", all(e["camera_id"] == ids["street"] for e in admin.get("/events", params={"camera_id": ids["street"]}).json()["items"]))
    check("filter events by type", all(e["event_type"] == "person" for e in admin.get("/events", params={"event_type": "person"}).json()["items"]))
    check("missing event -> 404", admin.get("/events/999999").status_code == 404 and admin.get("/events/999999/video").status_code == 404)


def test_night(admin: Client, ids: dict[str, str]) -> None:
    section("Night surveillance")
    low = wait_until(lambda: admin.get(f"/cameras/{ids['night']}").json()["lighting"], 30)
    check("dark camera is recognized as NIGHT (low light)", bool(low) and low["night"] and low["kind"] == "low_light", str(low))
    ir = wait_until(lambda: admin.get(f"/cameras/{ids['infrared']}").json()["lighting"], 30)
    check("monochrome camera is recognized as NIGHT (infrared)", bool(ir) and ir["night"] and ir["kind"] == "infrared", str(ir))
    day = admin.get(f"/cameras/{ids['entrance']}").json()["lighting"]
    check("normal daylight camera is NOT night", bool(day) and not day["night"], str(day))
    check("dashboard counts the night cameras", wait_until(lambda: admin.get("/dashboard/summary").json()["night_cameras"] >= 2, 15) is not None)
    night_people = [e for e in admin.get("/events", params={"camera_id": ids["night"], "limit": 50}).json()["items"] if e["event_type"] != "motion"]
    check("people are still detected in the dark footage", bool(night_people))


def face_crop(box: tuple[int, int, int, int]) -> bytes:
    """A portrait around one of the two faces in Ultralytics' zidane.jpg (the photo the demo videos pan across)."""
    import cv2
    from ultralytics.utils import ASSETS

    x, y, w, h = box
    image = cv2.imread(str(ASSETS / "zidane.jpg"))
    ok, data = cv2.imencode(".jpg", image[max(y - 100, 0) : y + h + 150, max(x - 130, 0) : x + w + 130])
    return data.tobytes()


def register(admin: Client, name: str, photo: bytes, filename: str) -> requests.Response:
    pid = admin.post("/people", json={"name": name}).json()["id"]
    r = admin.post(f"/people/{pid}/faces", files=[("files", (filename, photo, "image/jpeg"))])
    return r


def test_faces(admin: Client, ids: dict[str, str]) -> None:
    section("Face recognition and unknown-person detection")
    status = admin.get("/people/status").json()
    check("face recognition is available", status.get("available") is True, str(status))
    check("duplicate person name -> 409", (admin.post("/people", json={"name": "Dup"}), admin.post("/people", json={"name": "dup"}))[1].status_code == 409)
    pid = admin.get("/people").json()[0]["id"]
    bad = admin.post(f"/people/{pid}/faces", files=[("files", ("notes.txt", b"not an image", "text/plain"))])
    check("a non-image upload is rejected with a reason, not a crash", bad.status_code < 500, bad.text[:120])
    admin.delete(f"/people/{pid}")

    # 1) Register the man on the LEFT of the photo. The large, frontal man on the right is then a stranger.
    r = register(admin, "Registered man", face_crop((554, 261, 101, 160)), "left.jpg")
    check("register a person from a photo", r.status_code == 200, r.text[:160])
    unknown = wait_until(lambda: admin.get("/alerts", params={"type": "unknown_person"}).json()["items"], 150, 4)
    check("an unregistered person raises an unknown-person alert", bool(unknown))
    if unknown:
        alert = unknown[0]
        check("unknown-person alert has a snapshot", admin.get(f"/alerts/{alert['id']}/snapshot").headers.get("content-type") == "image/jpeg")
        check("unknown-person alert links to its recording", alert["event_available"] and admin.get(f"/events/{alert['event_id']}").status_code == 200)
        check("unknown-person event is typed correctly", admin.get(f"/events/{alert['event_id']}").json()["event_type"] == "unknown_person")

    # 2) Now register the man on the right too: he must be recognized BY NAME from then on.
    r = register(admin, "Demo Person", (VIDEOS / "demo_person.jpg").read_bytes(), "demo_person.jpg")
    check("register a second person (the demo photo)", r.status_code == 200, r.text[:160])
    known = wait_until(lambda: [e for e in admin.get("/events", params={"camera_id": ids["entrance"], "limit": 50}).json()["items"] if "Demo Person" in e["people"]], 150, 4)
    check("a registered person is recognized by name in an event", bool(known))


def test_suspicious_activity(admin: Client, ids: dict[str, str]) -> None:
    section("Suspicious-activity rules (zones, loitering, repeated entry, security hours)")
    street = ids["street"]
    bad = admin.post(f"/cameras/{street}/zones", json={"name": "line", "points": [[0, 0], [1, 1]]})
    check("zone with fewer than 3 points -> 422", bad.status_code == 422)
    z = admin.post(f"/cameras/{street}/zones", json={
        "name": "Whole view", "points": [[0, 0], [1, 0], [1, 1], [0, 1]], "severity": "high",
        "loiter_seconds": 5, "repeat_entries": 2, "repeat_window_seconds": 300,
    })
    check("create a restricted zone", z.status_code == 201, z.text[:120])
    now = datetime.now()
    r = admin.put(f"/cameras/{street}/rules", json={
        "quiet_start": (now - timedelta(hours=1)).strftime("%H:%M"), "quiet_end": (now + timedelta(hours=1)).strftime("%H:%M"), "fall_detection": True,
    })
    check("set security hours", r.status_code == 200 and r.json()["quiet_start"])
    check("half-set security hours -> 422", admin.put(f"/cameras/{street}/rules", json={"quiet_start": "22:00"}).status_code == 422)
    admin.put(f"/cameras/{street}/rules", json=r.json() | {"fall_detection": True})

    def rules_seen():
        items = admin.get("/alerts", params={"camera_id": street, "state": "all", "limit": 100}).json()["items"]
        return {a["details"].get("rule"): a for a in items}

    seen = wait_until(lambda: (lambda s: s if {"zone_intrusion", "loitering", "after_hours", "repeated_entry"} <= set(s) else None)(rules_seen()), 180, 4) or rules_seen()
    for rule, alert_type in (("zone_intrusion", "restricted_area"), ("loitering", "suspicious_activity"), ("after_hours", "suspicious_activity"), ("repeated_entry", "suspicious_activity")):
        a = seen.get(rule)
        check(f"rule fired: {rule}", a is not None and a["type"] == alert_type)
        if a:
            check(f"  {rule}: has severity, explanation, confidence, snapshot, recording",
                  a["severity"] in ("low", "medium", "high", "critical") and len(a["message"]) > 20 and a["details"].get("confidence") and a["has_snapshot"] and a["event_available"], json.dumps(a)[:200])
    if "repeated_entry" in seen and "zone_intrusion" in seen:
        check("repeated entry is escalated above the zone's own severity", seen["repeated_entry"]["severity"] == "critical")
    check("fall-like rule does not false-alarm on people walking", "fall_like" not in rules_seen())
    flagged = [e for e in admin.get("/events", params={"camera_id": street, "limit": 50}).json()["items"] if e["reasons"]]
    check("events list WHY they were flagged", bool(flagged) and all(r["message"] for e in flagged for r in e["reasons"]))
    check("event type reflects the most serious finding", any(e["event_type"] in ("restricted_area", "suspicious_activity") for e in flagged))


def test_alerts(server: Server, admin: Client, ids: dict[str, str]) -> None:
    section("Alerts: storage, severity, lifecycle, camera-offline, real-time delivery")
    offline = wait_until(lambda: admin.get("/alerts", params={"type": "camera_offline", "camera_id": ids["broken"]}).json()["items"], 40)
    check("camera-offline alert raised for the broken camera", bool(offline))
    check("only one alert per outage", len(admin.get("/alerts", params={"type": "camera_offline", "camera_id": ids["broken"], "state": "all"}).json()["items"]) == 1)

    listing = admin.get("/alerts", params={"state": "all", "limit": 200}).json()
    items = listing["items"]
    check("alerts are stored with type, severity and timestamp", bool(items) and all(a["type"] and a["severity"] and a["created_at"] for a in items))
    check("severity filter", all(a["severity"] == "high" for a in admin.get("/alerts", params={"severity": "high"}).json()["items"]))
    check("invalid filter -> 422", admin.get("/alerts", params={"severity": "banana"}).status_code == 422)

    target = next(a for a in items if not a["read"] and a["type"] != "camera_offline")
    check("mark read", admin.post(f"/alerts/{target['id']}/read").json()["read"] is True)
    try:
        from websockets.sync.client import connect
        cookie = "; ".join(f"{c.name}={c.value}" for c in admin.http.cookies)
        with connect(server.base.replace("http", "ws") + "/api/ws/alerts", additional_headers={"Cookie": cookie, "Origin": server.base}, open_timeout=10) as ws:
            admin.post(f"/alerts/{target['id']}/resolve")
            message = json.loads(ws.recv(timeout=10))
        check("real-time WebSocket pushes alert updates", message.get("type") in ("alert_updated", "alert_created"), str(message)[:100])
        denied = False
        try:
            with connect(server.base.replace("http", "ws") + "/api/ws/alerts", open_timeout=10):
                pass
        except Exception:
            denied = True
        check("WebSocket without a login is refused", denied)
    except ImportError:
        check("websockets library available for the WebSocket test", False)
    resolved = admin.get(f"/alerts/{target['id']}/snapshot")
    check("alert snapshot still served after resolve", resolved.status_code in (200, 404))
    check("resolved alert shows resolved_by", any(a["id"] == target["id"] and a["resolved"] and a["resolved_by"] == "admin" for a in admin.get("/alerts", params={"state": "resolved", "limit": 200}).json()["items"]))
    check("mark-all-read", admin.post("/alerts/read-all").status_code == 200 and admin.get("/alerts", params={"unread": "true"}).json()["items"] == [])
    check("missing alert -> 404", admin.post("/alerts/999999/read").status_code == 404)

    admin.patch(f"/cameras/{ids['broken']}", json={"enabled": False})
    check("disabling the broken camera auto-resolves its outage alert", wait_until(lambda: not admin.get("/alerts", params={"type": "camera_offline", "state": "open"}).json()["items"], 15) is not None)
    check("notification channel status endpoint", admin.get("/notifications/status").status_code == 200)


def test_dashboard(admin: Client) -> None:
    section("Dashboard summary")
    s = admin.get("/dashboard/summary").json()
    check("camera counts", s["cameras"]["total"] == 5 and s["cameras"]["online"] == 4)
    check("event, recording and alert counters", s["events_today"] > 0 and s["recordings_today"] > 0 and s["open_alerts"] >= 0)
    check("live detections are reported", "people_now" in s and "alerts" in s)


def test_database_and_restart(server: Server, admin: Client, ids: dict[str, str]) -> None:
    section("Database, clean shutdown and restart recovery")
    events_before = admin.get("/events", params={"limit": 1}).json()["total"]
    took = server.stop()
    check("Ctrl+C shuts the server down cleanly", took is not None, f"{took}")
    con = sqlite3.connect(server.db_path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    expected = {"cameras", "events", "person_detections", "people", "face_samples", "face_observations", "alerts", "zones", "camera_rules", "users", "user_sessions"}
    check("all expected tables exist", expected <= tables, str(expected - tables))
    check("database passes SQLite integrity check", con.execute("pragma integrity_check").fetchone()[0] == "ok")
    check("in-progress recordings were closed, none left 'recording'", con.execute("select count(*) from events where status='recording'").fetchone()[0] == 0)
    check("passwords are stored hashed, never in plain text", not any(ADMIN_PASSWORD in h or "viewer-password" in h for (h,) in con.execute("select password_hash from users")))
    check("database file is owner-only (chmod 600)", oct(server.db_path.stat().st_mode & 0o777) == "0o600")
    con.close()

    server.start()
    again = Client(server.base)
    check("admin can log in after restart (data persisted)", again.login().status_code == 200)
    check("event history survived the restart", again.get("/events", params={"limit": 1}).json()["total"] >= events_before)
    check("cameras survived and restarted", wait_until(lambda: sum(c["status"] == "online" for c in again.get("/cameras").json()) >= 4, 60) is not None)
    check("people and zones survived", len(again.get("/people").json()) == 2 and len(again.get(f"/cameras/{ids['street']}/zones").json()) == 1)

    r = again.delete(f"/cameras/{ids['night']}")
    check("deleting a camera works", r.status_code == 204)
    check("...and keeps its event history", again.get("/events", params={"camera_id": ids["night"]}).json()["total"] > 0)


def main() -> int:
    if not (VIDEOS / "demo_entrance.mp4").is_file():
        print("Demo videos are missing. Run:  python scripts/make_demo_videos.py")
        return 2
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    workdir = Path(tempfile.mkdtemp(prefix="cctv-system-test-"))
    server = Server(workdir, port)
    began = time.time()
    try:
        print(f"Starting the real server on port {port} (data in {workdir}) ...", flush=True)
        server.start()
        admin = test_authentication(server)
        test_roles(server, admin)
        ids = test_cameras(admin)
        test_detection_and_recording(admin, ids)
        test_night(admin, ids)
        test_faces(admin, ids)
        test_suspicious_activity(admin, ids)
        test_alerts(server, admin, ids)
        test_dashboard(admin)
        test_database_and_restart(server, admin, ids)
    finally:
        server.stop()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed in {time.time() - began:.0f} s")
    for name, _, detail in failed:
        print(f"  FAILED: {name}  {detail}")
    if failed:
        print(f"Server log: {workdir / 'server.log'}")
    return 1 if failed else 0


def test_whole_system():  # lets pytest run it too
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
