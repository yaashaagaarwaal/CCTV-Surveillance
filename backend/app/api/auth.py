import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import User
from app.db.session import SessionLocal
from app.security.bootstrap import effective_cookie_secure
from app.security.deps import client_ip, current_user, require_admin, session_token
from app.security.passwords import DUMMY_HASH, hash_password, password_problems, verify_password
from app.security.sessions import AuthUser, create_session, revoke_token, revoke_user_sessions
from app.security.throttle import login_throttle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _user_dict(user: User | AuthUser) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    ip = client_ip(request)
    username = body.username.strip().lower()

    wait = login_throttle.retry_after(ip, username)
    if wait:
        logger.warning("Login throttled for %r from %s", username, ip)
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {wait} s.", headers={"Retry-After": str(wait)})

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        # Always do one password check, even for unknown users (timing).
        valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
        if not (user and valid and not user.disabled):
            login_throttle.failed(ip, username)
            logger.warning("Failed login for %r from %s", username, ip)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        result = _user_dict(user)
        user_id = user.id

    login_throttle.succeeded(ip, username)
    token = create_session(user_id, ip, request.headers.get("user-agent"))
    response.set_cookie(
        settings.security.cookie_name,
        token,
        httponly=True,  # not readable by page scripts, so XSS can't steal it
        secure=effective_cookie_secure(),  # HTTPS only when configured / remote
        samesite="strict",  # never sent on cross-site requests
        path="/",
    )
    logger.info("User %r logged in from %s", username, ip)
    return result


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    revoke_token(session_token(request))
    response.delete_cookie(settings.security.cookie_name, path="/")
    return Response(status_code=204)


@router.get("/me")
def me(user: AuthUser = Depends(current_user)):
    return _user_dict(user)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordBody, request: Request, user: AuthUser = Depends(current_user)):
    with SessionLocal() as db:
        row = db.get(User, user.id)
        if not verify_password(body.current_password, row.password_hash):
            raise HTTPException(status_code=403, detail="Current password is incorrect")
        problems = password_problems(body.new_password, row.username)
        if problems:
            raise HTTPException(status_code=422, detail="New password " + "; ".join(problems))
        row.password_hash = hash_password(body.new_password)
        db.commit()
    revoke_user_sessions(user.id, except_token=session_token(request))  # sign out other devices
    logger.info("User %r changed their password", user.username)
    return Response(status_code=204)


# ---- user administration (admin only) -------------------------------------


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = Field(default="viewer", pattern="^(admin|viewer)$")


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|viewer)$")
    disabled: bool | None = None
    password: str | None = None


def _enabled_admin_count(db, excluding: int | None = None) -> int:
    stmt = select(func.count()).select_from(User).where(User.role == "admin", User.disabled.is_(False))
    if excluding is not None:
        stmt = stmt.where(User.id != excluding)
    return db.scalar(stmt) or 0


@users_router.get("")
def list_users():
    with SessionLocal() as db:
        return [
            {**_user_dict(u), "disabled": u.disabled, "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None}
            for u in db.scalars(select(User).order_by(User.username))
        ]


@users_router.post("", status_code=201)
def create_user(body: UserCreate):
    username = body.username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=422, detail="Username must be 3-32 characters: letters, numbers, . _ -")
    problems = password_problems(body.password, username)
    if problems:
        raise HTTPException(status_code=422, detail="Password " + "; ".join(problems))
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            raise HTTPException(status_code=409, detail=f"User '{username}' already exists")
        user = User(username=username, password_hash=hash_password(body.password), role=body.role)
        db.add(user)
        db.commit()
        return _user_dict(user)


@users_router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: AuthUser = Depends(require_admin)):
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        losing_admin = user.role == "admin" and not user.disabled and (body.role == "viewer" or body.disabled is True)
        if losing_admin and _enabled_admin_count(db, excluding=user_id) == 0:
            raise HTTPException(status_code=409, detail="There must be at least one enabled administrator")
        if user_id == admin.id and body.disabled:
            raise HTTPException(status_code=409, detail="You can't disable your own account")
        if body.password is not None:
            problems = password_problems(body.password, user.username)
            if problems:
                raise HTTPException(status_code=422, detail="Password " + "; ".join(problems))
            user.password_hash = hash_password(body.password)
        if body.role is not None:
            user.role = body.role
        if body.disabled is not None:
            user.disabled = body.disabled
        db.commit()
        result = _user_dict(user)
    if body.password is not None or body.disabled or body.role is not None:
        revoke_user_sessions(user_id)  # changed credentials/permissions: sign them out
    return result


@users_router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, admin: AuthUser = Depends(require_admin)):
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user_id == admin.id:
            raise HTTPException(status_code=409, detail="You can't delete your own account")
        if user.role == "admin" and _enabled_admin_count(db, excluding=user_id) == 0:
            raise HTTPException(status_code=409, detail="There must be at least one enabled administrator")
        revoke_user_sessions(user_id)
        db.delete(user)
        db.commit()
    return Response(status_code=204)
