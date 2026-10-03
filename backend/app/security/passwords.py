import base64
import hashlib
import hmac
import secrets

from app.core.config import settings

# scrypt (memory-hard, in the standard library): n=2^14, r=8, p=1 uses ~16 MB
# and takes ~50-100 ms per check — cheap for a login, costly to brute-force.
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32

_COMMON = {
    "password", "password1", "password123", "123456789", "1234567890", "qwertyuiop",
    "iloveyou", "admin12345", "administrator", "letmein123", "changeme123", "welcome123",
}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the username doesn't exist, so a login attempt takes
# the same time either way and can't be used to discover valid usernames.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problems(password: str, username: str = "") -> list[str]:
    """Reasons a password is unacceptable (empty list = fine)."""
    problems = []
    minimum = settings.security.min_password_length
    if len(password) < minimum:
        problems.append(f"must be at least {minimum} characters")
    if password.lower() in _COMMON or (username and password.lower() == username.lower()):
        problems.append("is too common or matches the username")
    if len(set(password)) < 5:
        problems.append("needs more variety of characters")
    return problems
