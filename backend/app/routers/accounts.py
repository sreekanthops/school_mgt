"""Auth, school profile, superadmin school management, and user/permission management."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import next_code
from ..models import School, Staff, Student, User
from ..schemas import LoginIn, PasswordChangeIn, SchoolIn, UserIn, UserUpdateIn
from ..security import (ALL_PERMS, PERMISSIONS, create_token, current_user, gen_password, hash_password,
                        is_locked, need, perm_set, record_failure, school_user,
                        subscription_info, verify_password)

router = APIRouter(prefix="/api")
log = logging.getLogger("school.admin")


def _me(user: User, db: Session) -> dict:
    school = db.get(School, user.school_id) if user.school_id else None
    return {
        "id": user.id, "username": user.username, "name": user.full_name, "role": user.role,
        "permissions": sorted(perm_set(user)), "student_id": user.student_id, "staff_id": user.staff_id,
        "school": {"id": school.id, "name": school.name} if school else None,
        # reminders and the read-only lock apply to owners and staff only, never to students
        "subscription": subscription_info(school.subscription_end) if school and user.role != "student" else None,
    }


# ---------- auth ----------
@router.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    if is_locked(data.username):
        raise HTTPException(429, "Too many failed attempts. Try again later.")
    user = db.scalar(select(User).where(User.username == data.username))
    ok = user and user.active and verify_password(data.password, user.password_hash)
    if ok and user.school_id:
        school = db.get(School, user.school_id)
        if not school or not school.active:
            raise HTTPException(403, "This school account is disabled")
    if not ok:
        record_failure(data.username)
        raise HTTPException(401, "Invalid username or password")
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"token": create_token(user), **_me(user, db)}


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _me(user, db)


@router.post("/auth/password", status_code=204)
def change_password(data: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    db.commit()


@router.get("/permissions")
def permissions(_: User = Depends(current_user)):
    return [{"key": k, "label": v} for k, v in PERMISSIONS.items()]


# ---------- school profile (tenant) ----------
def _school_out(s: School) -> dict:
    return {"id": s.id, "name": s.name, "about": s.about, "mission": s.mission, "vision": s.vision,
            "address": s.address, "contact": s.contact, "founded": s.founded}


@router.get("/school")
def get_school(user: User = Depends(school_user), db: Session = Depends(get_db)):
    return _school_out(db.get(School, user.school_id))


@router.put("/school")
def update_school(data: SchoolIn, user: User = Depends(need("school.manage")), db: Session = Depends(get_db)):
    s = db.get(School, user.school_id)
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return _school_out(s)


# ---------- users & permissions (tenant) ----------
def _user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "permissions": sorted(perm_set(u)) if u.role == "staff" else (["all"] if u.role == "admin" else []),
            "student_id": u.student_id, "staff_id": u.staff_id, "active": u.active}


def _check_perms(actor: User, perms: list[str]) -> str:
    bad = [p for p in perms if p not in ALL_PERMS]
    if bad:
        raise HTTPException(422, f"Unknown permission: {bad[0]}")
    mine = perm_set(actor)
    if any(p not in mine for p in perms):
        raise HTTPException(403, "You cannot grant permissions you do not have")
    if "users.manage" in perms and actor.role != "admin":
        raise HTTPException(403, "Only the school admin can grant user management")
    return ",".join(sorted(set(perms)))


def _target(db: Session, actor: User, uid: int) -> User:
    u = db.get(User, uid)
    if not u or u.school_id != actor.school_id:
        raise HTTPException(404, "Not found")
    if u.role == "admin" and actor.role != "admin":
        raise HTTPException(403, "Only a school admin can change an admin account")
    return u


@router.get("/users")
def list_users(actor: User = Depends(need("users.manage")), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.school_id == actor.school_id).order_by(User.role, User.username))
    return [_user_out(u) for u in rows]


@router.post("/users", status_code=201)
def create_user(data: UserIn, actor: User = Depends(need("users.manage")), db: Session = Depends(get_db)):
    if data.role == "admin" and actor.role != "admin":
        raise HTTPException(403, "Only a school admin can create another admin")
    perms = _check_perms(actor, data.permissions) if data.role == "staff" else None
    student_id = staff_id = None
    username = data.username
    if data.role == "admin":
        username = next_code(db, actor.school_id, "o")  # owner IDs: <school><year>o<nnn>
    if data.role == "student":
        st = db.get(Student, data.student_id) if data.student_id else None
        if not st or st.school_id != actor.school_id:
            raise HTTPException(422, "Choose a student from this school")
        student_id = st.id
        username = st.admission_no  # students always sign in with their student ID
    if data.staff_id:
        sf = db.get(Staff, data.staff_id)
        if not sf or sf.school_id != actor.school_id:
            raise HTTPException(422, "Choose a staff member from this school")
        staff_id = sf.id
        if data.role == "staff":
            username = sf.employee_id  # staff sign in with their staff ID
    if not username:
        raise HTTPException(422, "Username is required for staff without a staff profile")
    pw = gen_password()
    u = User(school_id=actor.school_id, username=username, password_hash=hash_password(pw), role=data.role,
             full_name=data.full_name, permissions=perms, student_id=student_id, staff_id=staff_id)
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username already exists, or that student already has a login")
    return {**_user_out(u), "temp_password": pw}


@router.put("/users/{uid}")
def update_user(uid: int, data: UserUpdateIn, actor: User = Depends(need("users.manage")),
                db: Session = Depends(get_db)):
    u = _target(db, actor, uid)
    if data.full_name is not None:
        u.full_name = data.full_name
    if data.permissions is not None:
        if u.role != "staff":
            raise HTTPException(422, "Permissions apply to staff accounts only")
        u.permissions = _check_perms(actor, data.permissions)
    if data.active is not None:
        if u.id == actor.id and not data.active:
            raise HTTPException(422, "You cannot deactivate yourself")
        u.active = data.active
    db.commit()
    return _user_out(u)


@router.post("/users/{uid}/reset-password")
def reset_password(uid: int, actor: User = Depends(need("users.manage")), db: Session = Depends(get_db)):
    u = _target(db, actor, uid)
    pw = gen_password()
    u.password_hash = hash_password(pw)
    db.commit()
    return {"username": u.username, "temp_password": pw}


@router.delete("/users/{uid}", status_code=204)
def delete_user(uid: int, actor: User = Depends(need("users.manage")), db: Session = Depends(get_db)):
    u = _target(db, actor, uid)
    if u.id == actor.id:
        raise HTTPException(422, "You cannot delete yourself")
    db.delete(u)
    db.commit()
