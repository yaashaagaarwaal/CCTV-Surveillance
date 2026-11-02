"""Data-handling hardening found by the reliability audit. Each test fails if its fix is removed.

  * a mistyped password in the username box must never reach the log
  * a face photo that declares gigapixels is refused before it is decoded
  * a stored file path can never point outside the storage folder
  * a world-readable .env (admin password, secret key) is warned about

Run:  python -m tests.test_security_hardening
"""
import io
import logging
import os
import stat
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["ADMIN_PASSWORD"] = "hardening-test-password-123"
os.environ["SECRET_KEY"] = "hardening-test-secret-key-0123456789-abcdef"

import cv2  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402
from PIL import Image  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.api import people as people_api  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.models import Person  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.api.auth import LoginBody, login  # noqa: E402
from app.security.bootstrap import ensure_admin, env_file_warning  # noqa: E402
from app.services.faces.service import EnrollError  # noqa: E402
from app.services.faces.storage import resolve  # noqa: E402
from app.services.recording.paths import resolve_recording_path  # noqa: E402

CANARY = "typed-my-password-here-7f3a9c"


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def test_a_mistyped_password_in_the_username_box_is_not_logged():
    def attempt(username: str, password: str) -> int:
        scope = {"type": "http", "method": "POST", "path": "/api/auth/login", "headers": [(b"user-agent", b"test")], "client": ("127.0.0.1", 50000), "query_string": b""}
        try:
            login(LoginBody(username=username, password=password), Request(scope), Response())
            return 200
        except HTTPException as exc:
            return exc.status_code

    handler = Capture()
    logging.getLogger().addHandler(handler)
    try:
        codes = [attempt(CANARY, "x") for _ in range(settings.security.login_max_failures + 2)]  # also runs into the throttle
        assert codes[0] == 401 and codes[-1] == 429, codes
        attempt("admin", "wrong-on-purpose-1")
    finally:
        logging.getLogger().removeHandler(handler)
    text = "\n".join(handler.lines)
    assert "Failed login" in text and "Login throttled" in text, "the failures must still be logged"
    assert CANARY not in text, "the text typed into the username box must not be written to the log"
    assert "'admin'" in text, "a real account's name is still logged, so failed attempts remain traceable"


class StubService:
    def reload_gallery(self):
        pass


def _png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("L", (width, height)).save(out, "PNG")  # all black: a few KB however big it is
    return out.getvalue()


def test_a_gigapixel_photo_is_refused_before_it_is_decoded():
    with SessionLocal() as db:
        person = Person(name="Upload test")
        db.add(person)
        db.commit()
        person_id = person.id
    decoded = []
    real_imdecode = cv2.imdecode
    cv2.imdecode = lambda *a, **k: decoded.append(1) or real_imdecode(*a, **k)
    try:
        huge = _png(7000, 7000)  # 49 megapixels, over the 40 MP limit, yet only a few KB
        assert len(huge) < settings.face.enroll_max_image_bytes, "small on disk, which is the whole point"
        results = people_api._process_uploads(StubService(), person_id, [("huge.png", huge)])["results"]
        assert not results[0]["ok"] and "megapixels" in results[0]["error"], results
        assert decoded == [], "an over-size photo must not be decoded"

        small = _png(200, 200)
        original = people_api._enroll_image
        people_api._enroll_image = lambda *a, **k: (_ for _ in ()).throw(EnrollError("No face found in this photo"))
        try:
            results = people_api._process_uploads(StubService(), person_id, [("small.png", small)])["results"]
        finally:
            people_api._enroll_image = original
        assert results[0]["error"] == "No face found in this photo", "a normal-size photo still goes on to face checking"
        assert decoded == [1]
    finally:
        cv2.imdecode = real_imdecode


def test_stored_paths_cannot_leave_the_storage_folder():
    root = settings.storage_dir
    root.mkdir(parents=True, exist_ok=True)
    assert resolve_recording_path("recordings/cam1/2025-01-01/a.mp4").is_relative_to(root.resolve())
    for hostile in ("../../etc/passwd", "recordings/../../outside.mp4", "/etc/passwd"):
        for func in (resolve, resolve_recording_path):
            try:
                func(hostile)
            except ValueError:
                continue
            raise AssertionError(f"{func.__name__}({hostile!r}) must be refused")
    outside = Path(tempfile.mkdtemp())
    (root / "link").symlink_to(outside)
    try:
        resolve("link/secret.jpg")
    except ValueError:
        pass
    else:
        raise AssertionError("a symlink inside storage must not lead outside it")
    finally:
        (root / "link").unlink()


def test_a_world_readable_env_file_is_warned_about():
    env = Path(tempfile.mkdtemp()) / ".env"
    env.write_text("ADMIN_PASSWORD=not-a-real-password\n")
    env.chmod(0o644)
    warning = env_file_warning(env)
    assert warning and "chmod 600" in warning and "not-a-real-password" not in warning
    env.chmod(0o600)
    assert env_file_warning(env) is None, "owner-only is fine"
    env.chmod(0o640)
    assert env_file_warning(env), "group-readable is still readable by others"
    assert env_file_warning(env.parent / "missing") is None
    assert stat.S_IMODE(env.stat().st_mode) == 0o640


def main() -> int:
    init_db()
    ensure_admin()
    failures = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try:
            func()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print("hardening holds" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
