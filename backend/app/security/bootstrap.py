import logging
import secrets

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import User
from app.db.session import SessionLocal
from app.security.passwords import hash_password, password_problems

logger = logging.getLogger(__name__)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def effective_cookie_secure() -> bool:
    return settings.cookie_secure or settings.remote_mode


def docs_enabled() -> bool:
    return settings.enable_docs and not settings.remote_mode


def config_problems() -> list[str]:
    """Why the current configuration is unsafe. Wildcard CORS with cookies is
    refused in every mode; REMOTE_MODE adds the checks that matter once the
    server is reachable from a network."""
    problems = []
    if "*" in settings.cors_origins:
        problems.append("CORS_ORIGINS must not contain '*' (cookies are used, so origins must be listed explicitly)")
    if settings.admin_password:
        bad = password_problems(settings.admin_password, settings.admin_username)
        if bad:
            problems.append("ADMIN_PASSWORD " + "; ".join(bad))

    if settings.remote_mode:
        public_hosts = [h for h in settings.allowed_hosts if h not in LOCAL_HOSTS]
        if "*" in settings.allowed_hosts or not public_hosts:
            problems.append("ALLOWED_HOSTS must list your public host name(s) (no '*') in remote mode")
        for origin in settings.cors_origins:
            if not origin.startswith("https://") and "localhost" not in origin and "127.0.0.1" not in origin:
                problems.append(f"CORS origin {origin} must be https:// in remote mode")
        if settings.public_url and not settings.public_url.startswith("https://"):
            problems.append("PUBLIC_URL must be https:// in remote mode")
        if len(settings.secret_key) < 32:
            problems.append("SECRET_KEY (>= 32 characters) must be set explicitly in remote mode")
    return problems


def validate_security_config() -> None:
    problems = config_problems()
    if problems:
        message = "Refusing to start — unsafe configuration:\n  - " + "\n  - ".join(problems)
        if settings.remote_mode or any("CORS" in p or "ADMIN_PASSWORD" in p for p in problems):
            raise RuntimeError(message)
        logger.warning(message)
    if settings.remote_mode:
        logger.info("REMOTE_MODE on: secure cookies, docs disabled, HSTS enabled. Make sure TLS terminates in front of this server.")


def ensure_admin() -> None:
    """First start only: create the administrator account."""
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        username = settings.admin_username.strip().lower()
        password = settings.admin_password
        generated = not password
        if generated:
            if settings.remote_mode:
                raise RuntimeError("Set ADMIN_PASSWORD for the first start in remote mode (no password is printed to logs there)")
            password = secrets.token_urlsafe(12)
        db.add(User(username=username, password_hash=hash_password(password), role="admin"))
        db.commit()
    if generated:
        banner = "=" * 62
        logger.warning(
            "\n%s\n  FIRST RUN: administrator account created\n    username: %s\n    password: %s\n"
            "  Shown once. Log in and change it (or set ADMIN_PASSWORD before first start).\n%s",
            banner, username, password, banner,
        )
    else:
        logger.info("Administrator '%s' created from ADMIN_PASSWORD", username)
