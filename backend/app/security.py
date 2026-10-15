import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
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
    "attendance.manage": "Mark attendance and see attendance reports",
    "announcements.manage": "Post and manage school announcements",
}
ALL_PERMS = set(PERMISSIONS)
TEACHER_DEFAULT = ["students.view", "marks.edit", "attendance.manage"]
PRINCIPAL_DEFAULT = TEACHER_DEFAULT + ["fees.view", "announcements.manage"]


def perm_set(user: User) -> set:
    """admin (school owner) holds every permission; staff holds what was granted; others none."""
    if user.role == "admin":
        return set(ALL_PERMS)
    if user.role == "staff":
        return {p for p in (user.permissions or "").split(",") if p in ALL_PERMS}
    return set()


def hash_password(pw: str, rounds: int = 12) -> str:
    """`rounds` is only lowered for bulk-issued one-time passwords (see people.import_students)."""
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def gen_password() -> str:
    """One-time password. Never starts with - or _, so it stays exact when listed in a spreadsheet."""
    while True:
        pw = secrets.token_urlsafe(9)
        if pw[0].isalnum():
            return pw


def is_locked(username: str, limit: int = MAX_FAILS) -> bool:
    now = time.time()
    _fails[username] = [t for t in _fails[username] if now - t < LOCK_SECONDS]
    return len(_fails[username]) >= limit


_hits = defaultdict(list)  # key -> [timestamps] for plain request-rate limits


def rate_limit(key: str, limit: int) -> None:
    """Allow at most `limit` calls per key per 15 minutes; raises 429 beyond that."""
    now = time.time()
    _hits[key] = [t for t in _hits[key] if now - t < LOCK_SECONDS]
    if len(_hits[key]) >= limit:
        raise HTTPException(429, "Too many requests. Try again later.")
    _hits[key].append(now)


def anon_key(purpose: str, school_id: int, user_id: int) -> str:
    """Keyed hash used where the app must recognise 'the same person' without storing who they are."""
    return hmac.new(JWT_SECRET.encode(), f"{purpose}:{school_id}:{user_id}".encode(), hashlib.sha256).hexdigest()


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


# Subscription reminders go out this many days before the end date (reminder 1, 2 and 3).
REMINDER_DAYS = (30, 14, 7)
# Once a subscription has expired, owners and staff may still sign in and read, but cannot change anything.
# These stay open because they are not school-management actions: messaging, the assistant, own password.
LOCK_EXEMPT = ("/api/messages", "/api/chat", "/api/auth", "/api/announcements/read")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def subscription_info(end: Optional[date]) -> dict:
    """status: Active | Expiring | Expired | No expiry. reminder: 0 (none) or 1-3, rising as the end date nears."""
    if end is None:
        return {"status": "No expiry", "end": None, "days_left": None, "reminder": 0, "locked": False}
    left = (end - date.today()).days
    if left < 0:
        return {"status": "Expired", "end": end.isoformat(), "days_left": left, "reminder": 0, "locked": True}
    reminder = sum(1 for d in REMINDER_DAYS if left <= d)
    return {"status": "Expiring" if reminder else "Active", "end": end.isoformat(), "days_left": left,
            "reminder": reminder, "locked": False}


def school_user(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    """Any authenticated user that belongs to an active school (everyone except the superadmin).
    After the subscription ends, owners and staff are limited to read-only; students are never affected."""
    if user.role == "superadmin" or user.school_id is None:
        raise HTTPException(403, "Not available for this account")
    school = db.get(School, user.school_id)
    if not school or not school.active:
        raise HTTPException(403, "This school account is disabled")
    if user.must_change and not request.url.path.startswith("/api/auth"):
        raise HTTPException(403, "Please change your temporary password first")
    if (user.role != "student" and request.method not in SAFE_METHODS
            and subscription_info(school.subscription_end)["locked"]
            and not request.url.path.startswith(LOCK_EXEMPT)):
        raise HTTPException(403, "Subscription expired. The school is read-only until the platform team renews it.")
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
