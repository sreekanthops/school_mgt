import logging
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import JWT_EXPIRE_MINUTES, JWT_SECRET
from .db import get_db
from .models import School, User

log = logging.getLogger("school.security")
bearer = HTTPBearer(auto_error=False)

MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
_fails = defaultdict(list)  # username -> [timestamps]

PERMISSIONS = {
    "students.view": "View all students, marks and performance",
    "students.manage": "Add, edit, delete students and set their photos",
    "marks.edit": "Enter and edit marks",
    "fees.view": "View fee details",
    "fees.manage": "Set fees and record payments",
    "staff.manage": "Add, edit, delete staff",
    "subjects.manage": "Manage subjects and chapters",
    "content.manage": "Manage events, gallery and goals",
    "school.manage": "Edit school profile",
    "photos.approve": "Approve student photo requests",
    "users.manage": "Create users and set their permissions",
}
ALL_PERMS = set(PERMISSIONS)
TEACHER_DEFAULT = ["students.view", "marks.edit"]


def perm_set(user: User) -> set:
    """admin (school owner) holds every permission; staff holds what was granted; others none."""
    if user.role == "admin":
        return set(ALL_PERMS)
    if user.role == "staff":
        return {p for p in (user.permissions or "").split(",") if p in ALL_PERMS}
    return set()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def gen_password() -> str:
    return secrets.token_urlsafe(9)


def is_locked(username: str) -> bool:
    now = time.time()
    _fails[username] = [t for t in _fails[username] if now - t < LOCK_SECONDS]
    return len(_fails[username]) >= MAX_FAILS


def record_failure(username: str) -> None:
    _fails[username].append(time.time())
    log.warning("login_failed", extra={"username": username[:50]})


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, JWT_SECRET, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    if not user or not user.active:
        raise HTTPException(401, "Invalid or expired token")
    return user


def school_user(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    """Any authenticated user that belongs to an active school (everyone except the superadmin)."""
    if user.role == "superadmin" or user.school_id is None:
        raise HTTPException(403, "Not available for this account")
    school = db.get(School, user.school_id)
    if not school or not school.active:
        raise HTTPException(403, "This school account is disabled")
    return user


def staff_side(user: User = Depends(school_user)) -> User:
    if user.role == "student":
        raise HTTPException(403, "Not available for student accounts")
    return user


def need(*perms: str):
    """Dependency: user must hold at least one of the given permissions."""
    wanted = set(perms)

    def dep(user: User = Depends(school_user)) -> User:
        if not (perm_set(user) & wanted):
            log.warning("forbidden", extra={"user_id": user.id, "needs": ",".join(perms)})
            raise HTTPException(403, "You do not have permission to do this")
        return user

    return dep


def superadmin_only(user: User = Depends(current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(403, "Superadmin access required")
    return user
