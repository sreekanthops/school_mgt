import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import JWT_EXPIRE_MINUTES, JWT_SECRET
from .db import get_db
from .models import User

log = logging.getLogger("school.security")
bearer = HTTPBearer(auto_error=False)

MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
_fails = defaultdict(list)  # username -> [timestamps]


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


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
        user = db.scalar(select(User).where(User.id == int(payload["sub"])))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        log.warning("forbidden", extra={"user_id": user.id})
        raise HTTPException(403, "Admin access required")
    return user
