"""Soak test: the real server on a temporary database, six staged cameras with rules, left running.

While it runs it measures the server process (CPU, memory), the delay between an alert being stored and arriving on a
WebSocket, and afterwards checks what the dashboard would show: every alert's snapshot and recording evidence, event timestamps,
duplicates (two alerts for the same camera and rule closer together than their cooldown), false alerts in the empty room, what a
viewer account may not do, and that a camera password never reaches a viewer or the log.

SIMULATION: the cameras are looping video files (the staged clips). No real camera is involved.

Run from the backend folder:
    python scripts/soak_test.py                 # 240 s of soak, about 5 minutes in all
    python scripts/soak_test.py --seconds 60 --json
"""
import argparse
import json
import socket
import statistics
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from websockets.sync.client import connect  # noqa: E402

from tests.test_system import ADMIN_PASSWORD, VIDEOS, Client, Server, wait_until  # noqa: E402

RIGHT_HALF = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]
CANARY = "CANARY-pw-9f2c41"
COOLDOWN = {"zone_intrusion": 30, "loitering": 60, "repeated_entry": 300, "crowd": 30}  # as configured below / by default
CAMERAS = {
    "entry": ("Zone Entry", "demo_zone_entry.mp4", 24),
    "loiter": ("Zone Loiter", "demo_zone_loiter.mp4", 34),
    "crowd": ("Crowd", "demo_crowd.mp4", 30),
    "repeated": ("Repeated Entry", "demo_repeated.mp4", 70),
    "empty": ("Empty Room", "demo_empty.mp4", 20),
    "dim": ("Dim Room", "demo_lowlight_zone.mp4", 24),
}


def parse_utc(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def run(seconds: int) -> dict:
    missing = [c[1] for c in CAMERAS.values() if not (VIDEOS / c[1]).is_file()]
    if missing:
        raise SystemExit(f"Staged clips are missing ({missing}). Run: python scripts/make_demo_videos.py")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    workdir = Path(tempfile.mkdtemp(prefix="cctv-soak-"))
    server = Server(workdir, port, {
        "ACTIVITY__ZONE_ALERT_COOLDOWN_SECONDS": "30",  # shorter than the default 120 so several episodes happen in minutes
        "ACTIVITY__CROWD_ALERT_COOLDOWN_SECONDS": "30",
        "ACTIVITY__SUSPICIOUS_ALERT_COOLDOWN_SECONDS": "60",
        "ALERTS__CAMERA_OFFLINE_GRACE_SECONDS": "10",
    })
    report: dict = {"seconds": seconds, "findings": []}

    def finding(name: str, ok: bool, detail: str = "") -> None:
        report["findings"].append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""), flush=True)

    try:
        print(f"Starting the real server on port {port} ...", flush=True)
        server.start()
        admin = Client(server.base)
        assert admin.login().status_code == 200
        ids = {}
        for key, (name, clip, _) in CAMERAS.items():
            r = admin.post("/cameras", json={"name": name, "type": "file", "source": clip})
            ids[key] = r.json()["id"]
        zone_body = {"points": RIGHT_HALF, "severity": "high", "loiter_seconds": 0, "repeat_entries": 0}
        admin.post(f"/cameras/{ids['entry']}/zones", json={**zone_body, "name": "Right half"})
        admin.post(f"/cameras/{ids['dim']}/zones", json={**zone_body, "name": "Right half"})
        admin.post(f"/cameras/{ids['loiter']}/zones", json={**zone_body, "name": "Right half", "loiter_seconds": 10})
        admin.post(f"/cameras/{ids['repeated']}/zones", json={**zone_body, "name": "Right half", "repeat_entries": 3, "repeat_window_seconds": 300})
        admin.post(f"/cameras/{ids['empty']}/zones", json={**zone_body, "name": "Right half", "loiter_seconds": 5, "repeat_entries": 2})
        admin.put(f"/cameras/{ids['crowd']}/rules", json={"crowd_threshold": 3, "crowd_seconds": 8})
        admin.put(f"/cameras/{ids['empty']}/rules", json={"crowd_threshold": 2, "crowd_seconds": 3})
        bad = admin.post("/cameras", json={"name": "Hallway IP", "type": "rtsp", "source": f"rtsp://cctv:{CANARY}@127.0.0.1:9/none"}).json()["id"]
        online = wait_until(lambda: all(admin.get(f"/cameras/{ids[k]}").json()["status"] == "online" for k in ids), 90)
        finding("six staged cameras come online and the unreachable RTSP camera does not", bool(online) and admin.get(f"/cameras/{bad}").json()["status"] != "online")

        # ---- listen for alerts on the WebSocket, and sample the server's CPU and memory
        token = next(c.value for c in admin.http.cookies if c.name == "cctv_session")
        received, listener_errors, stop, connected = [], [], threading.Event(), {}

        def listen():
            try:
                with connect(f"ws://127.0.0.1:{port}/api/ws/alerts", additional_headers={"Cookie": f"cctv_session={token}", "Origin": server.base}, open_timeout=10) as ws:
                    connected["at"] = time.time()
                    while not stop.is_set():
                        try:
                            message = json.loads(ws.recv(timeout=1.0))
                        except TimeoutError:
                            continue  # nothing this second; the connection is still fine
                        if message.get("type") == "alert_created":
                            received.append((message["alert"], time.time()))
            except Exception as exc:  # noqa: BLE001 - recorded, not hidden: a dead listener must not look like a missing alert
                if not stop.is_set():
                    listener_errors.append(repr(exc))

        samples = []
        process = psutil.Process(server.proc.pid)
        process.cpu_percent(None)

        def sample():
            while not stop.is_set():
                samples.append((process.cpu_percent(None), process.memory_info().rss / 2**20))
                time.sleep(2)

        threads = [threading.Thread(target=listen, daemon=True), threading.Thread(target=sample, daemon=True)]
        for t in threads:
            t.start()
        began = time.time()
        print(f"Soaking for {seconds} s ...", flush=True)
        time.sleep(seconds)
        ended = time.time()
        stop.set()
        for t in threads:
            t.join(timeout=5)

        # ---- what happened
        alerts = admin.get("/alerts", params={"state": "all", "limit": 200}).json()["items"]
        by = {}
        for a in alerts:
            if a["type"] == "camera_offline":
                continue
            by.setdefault((a["camera_id"], a["details"].get("rule", a["type"])), []).append(parse_utc(a["created_at"]))
        name_of = {ids[k]: CAMERAS[k][0] for k in ids}
        report["alerts_by_camera_and_rule"] = {f"{name_of.get(c, c)} / {r}": len(v) for (c, r), v in sorted(by.items())}
        duplicates = []
        for (camera, rule), times in by.items():
            times.sort()
            limit = COOLDOWN.get(rule, 60) * 0.95
            duplicates += [f"{name_of.get(camera, camera)} / {rule}: {b - a:.0f} s apart" for a, b in zip(times, times[1:]) if b - a < limit]
        report["duplicate_alerts"] = duplicates
        finding("no duplicate alerts: nothing closer together than its cooldown", not duplicates, "; ".join(duplicates[:3]))
        empty_alerts = [a for a in alerts if a["camera_id"] == ids["empty"]]
        finding("the empty room raised no alert at all", not empty_alerts, f"{len(empty_alerts)} alerts")
        expected = {("entry", "zone_intrusion"), ("loiter", "zone_intrusion"), ("loiter", "loitering"), ("crowd", "crowd"), ("repeated", "repeated_entry"), ("dim", "zone_intrusion")}
        missing_rules = [f"{k}/{r}" for k, r in expected if (ids[k], r) not in by]
        finding("every staged scenario produced its alert", not missing_rules, f"missing {missing_rules}")

        # ---- WebSocket delivery
        # A WebSocket is a live feed: an alert stored before the listener connected could not have been pushed to it.
        stored_ids = {a["id"] for a in alerts if a["type"] != "camera_offline" and parse_utc(a["created_at"]) >= connected.get("at", 0) - 0.5}
        before_listener = sum(1 for a in alerts if a["type"] != "camera_offline" and parse_utc(a["created_at"]) < connected.get("at", 0) - 0.5)
        report["alerts_before_the_listener_connected"] = before_listener
        delays = []
        for alert, arrived in received:
            if alert["id"] in stored_ids:
                delays.append(arrived - parse_utc(alert["created_at"]))
        got = {a["id"] for a, _ in received}
        lost = sorted(stored_ids - got)
        by_id = {a["id"]: a for a in alerts}
        finding("every alert stored while the listener was connected also arrived over the WebSocket", not lost and not listener_errors,
                f"{len(lost)} of {len(stored_ids)} missing: " + ", ".join(f"#{i} ({by_id[i]['details'].get('rule')}, {parse_utc(by_id[i]['created_at']) - began:.0f}s into the run)" for i in lost[:5]) + f"; listener errors: {listener_errors}")
        report["websocket_delay_ms"] = {"median": round(statistics.median(delays) * 1000), "max": round(max(delays) * 1000)} if delays else None

        # ---- evidence behind the alerts
        no_snapshot, bad_event = [], []
        for a in alerts:
            if a["type"] == "camera_offline":
                continue
            if not a["has_snapshot"] or admin.get(f"/alerts/{a['id']}/snapshot").headers.get("content-type") != "image/jpeg":
                no_snapshot.append(a["id"])
            event = admin.get(f"/events/{a['event_id']}").json() if a.get("event_id") else None
            if not event or not (began - 20 <= parse_utc(event["timestamp"]) <= ended + 5) or not event["has_recording"]:
                bad_event.append(a["id"])
        finding("every alert has a snapshot image", not no_snapshot, str(no_snapshot[:5]))
        finding("every alert links to an event with a recording and a timestamp inside this run", not bad_event, str(bad_event[:5]))
        done = [e for e in admin.get("/events", params={"limit": 50}).json()["items"] if e["playable"]]
        ranged = admin.http.get(f"{server.base}/api/events/{done[0]['id']}/video", headers={"Range": "bytes=0-1023"}, timeout=20) if done else None
        finding("a finished recording can be played (HTTP range request)", bool(ranged) and ranged.status_code in (200, 206) and ranged.headers.get("content-type", "").startswith("video/"))

        # ---- viewer accounts and credentials
        admin.post("/users", json={"username": "viewer1", "password": "viewer-password-123", "role": "viewer"})
        viewer = Client(server.base)
        viewer.login("viewer1", "viewer-password-123")
        some_alert, some_zone = alerts[0]["id"], admin.get(f"/cameras/{ids['entry']}/zones").json()[0]["id"]
        attempts = [
            ("PUT", f"/cameras/{ids['crowd']}/rules", {"crowd_threshold": 9}), ("POST", f"/cameras/{ids['entry']}/zones", {**zone_body, "name": "x"}),
            ("DELETE", f"/zones/{some_zone}", None), ("POST", "/cameras", {"name": "x", "type": "file", "source": "demo_empty.mp4"}),
            ("PATCH", f"/cameras/{ids['entry']}", {"enabled": False}), ("DELETE", f"/cameras/{ids['entry']}", None),
            ("POST", "/users", {"username": "evil", "password": "evil-password-123", "role": "admin"}), ("GET", "/users", None),
            ("DELETE", f"/alerts/{some_alert}", None), ("POST", "/people", {"name": "x"}), ("DELETE", "/events/1", None),
        ]
        codes = [viewer.call(m, p, **({"json": b} if b is not None else {})).status_code for m, p, b in attempts]
        finding("a viewer is refused every administrative action tried (HTTP 403)", all(c == 403 for c in codes), str(codes))
        finding("the viewer can still read cameras and alerts", viewer.get("/cameras").status_code == 200 and viewer.get("/alerts").status_code == 200)
        seen_by_viewer = json.dumps([viewer.get("/cameras").json(), viewer.get(f"/cameras/{bad}").json()])
        seen_by_admin = admin.get(f"/cameras/{bad}").json()
        finding("a camera password never reaches a viewer, and the admin's display copy is masked",
                CANARY not in seen_by_viewer and CANARY not in json.dumps(seen_by_admin["source_display"]) and "****" in seen_by_admin["source_display"])
        offline = wait_until(lambda: [a for a in admin.get("/alerts", params={"type": "camera_offline", "camera_id": bad}).json()["items"]], 30, 2)
        finding("the unreachable camera is reported offline with an alert", bool(offline))
        admin.patch(f"/cameras/{bad}", json={"enabled": False})
        finding("disabling it resolves the outage alert", wait_until(lambda: not admin.get("/alerts", params={"type": "camera_offline", "state": "open", "camera_id": bad}).json()["items"], 15, 1) is not None)

        cpu = [c for c, _ in samples[2:]] or [0]
        rss = [m for _, m in samples]
        quarter = max(len(rss) // 4, 1)
        report["server_process"] = {
            "cpu_percent_of_one_core": {"median": round(statistics.median(cpu)), "max": round(max(cpu))},
            "rss_mb": {"median": round(statistics.median(rss)), "max": round(max(rss))},
            # A leak shows as memory still climbing at the end: compare the first and last quarter of the run (the first
            # minute is excluded from the start because models and buffers are still filling).
            "rss_mb_trend": {"second_quarter_median": round(statistics.median(rss[quarter : 2 * quarter] or rss)), "last_quarter_median": round(statistics.median(rss[-quarter:]))},
            "rss_mb_by_minute": [round(statistics.median(rss[i : i + 30])) for i in range(0, len(rss) - 14, 30)],
            "samples": len(samples),
        }
        report["alerts_total"] = len(stored_ids)
    finally:
        server.stop()
    log = (workdir / "server.log").read_text(errors="replace")
    finding("the server log contains no camera password and no admin password", CANARY not in log and ADMIN_PASSWORD not in log)
    errors = [line for line in log.splitlines() if "Traceback" in line or "database is locked" in line or " ERROR" in line or "Exception" in line]
    report["log_errors"] = errors[:5]
    finding("no tracebacks, errors or 'database is locked' in the server log", not errors, f"{len(errors)} lines; first: {errors[0][:100] if errors else ''}")
    report["passed"] = sum(f["ok"] for f in report["findings"])
    report["failed"] = [f["check"] for f in report["findings"] if not f["ok"]]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seconds", type=int, default=240)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    outcome = run(args.seconds)
    print(json.dumps({k: v for k, v in outcome.items() if k != "findings"}, indent=2))
    print(f"\n{outcome['passed']}/{len(outcome['findings'])} checks passed")
    sys.exit(1 if outcome["failed"] else 0)
