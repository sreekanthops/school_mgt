"""Auth, school profile, superadmin school management, and user/permission management."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import storage
from ..db import get_db
from ..models import School, Staff, Student, User
from ..schemas import LoginIn, NewSchoolIn, PasswordChangeIn, SchoolIn, UserIn, UserUpdateIn
from ..security import (ALL_PERMS, PERMISSIONS, create_token, current_user, gen_password, hash_password,
                        is_locked, need, perm_set, record_failure, school_user, superadmin_only,
                        verify_password)

router = APIRouter(prefix="/api")
log = logging.getLogger("school.admin")


def _me(user: User, db: Session) -> dict:
    school = db.get(School, user.school_id) if user.school_id else None
    return {
        "id": user.id, "username": user.username, "name": user.full_name, "role": user.role,
        "permissions": sorted(perm_set(user)), "student_id": user.student_id, "staff_id": user.staff_id,
        "school": {"id": school.id, "name": school.name} if school else None,
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


# ---------- superadmin: schools ----------
@router.get("/schools")
def list_schools(_: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    out = []
    for s in db.scalars(select(School).order_by(School.id)):
        owner = db.scalar(select(User).where(User.school_id == s.id, User.role == "admin").order_by(User.id))
        out.append({
            "id": s.id, "name": s.name, "active": s.active, "created_at": s.created_at.isoformat(),
            "students": db.scalar(select(func.count()).select_from(Student).where(Student.school_id == s.id)),
            "staff": db.scalar(select(func.count()).select_from(Staff).where(Staff.school_id == s.id)),
            "users": db.scalar(select(func.count()).select_from(User).where(User.school_id == s.id)),
            "owner": {"id": owner.id, "name": owner.full_name, "username": owner.username} if owner else None,
        })
    return out


@router.post("/schools", status_code=201)
def create_school(data: NewSchoolIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.username == data.owner_username)):
        raise HTTPException(409, "Username already exists")
    school = School(name=data.name)
    db.add(school)
    db.flush()
    pw = gen_password()
    owner = User(school_id=school.id, username=data.owner_username, password_hash=hash_password(pw),
                 role="admin", full_name=data.owner_name)
    db.add(owner)
    db.commit()
    log.info("school_created", extra={"school_id": school.id, "by": sa.id})
    return {"school": {"id": school.id, "name": school.name},
            "owner": {"username": owner.username, "temp_password": pw}}


@router.put("/schools/{school_id}/active")
def set_school_active(school_id: int, body: dict, _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = db.get(School, school_id)
    if not s:
        raise HTTPException(404, "Not found")
    s.active = bool(body.get("active"))
    db.commit()
    return {"id": s.id, "active": s.active}


@router.delete("/schools/{school_id}", status_code=204)
def delete_school(school_id: int, _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = db.get(School, school_id)
    if not s:
        raise HTTPException(404, "Not found")
    db.delete(s)
    db.commit()
    storage.remove_school(school_id)


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
    if data.role == "student":
        st = db.get(Student, data.student_id) if data.student_id else None
        if not st or st.school_id != actor.school_id:
            raise HTTPException(422, "Choose a student from this school")
        student_id = st.id
        username = st.admission_no  # students always sign in with their student ID
    elif not username:
        raise HTTPException(422, "Username is required")
    if data.staff_id:
        sf = db.get(Staff, data.staff_id)
        if not sf or sf.school_id != actor.school_id:
            raise HTTPException(422, "Choose a staff member from this school")
        staff_id = sf.id
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


# superadmin: reset an owner's password
@router.post("/schools/{school_id}/owner/reset-password")
def reset_owner_password(school_id: int, _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    owner: Optional[User] = db.scalar(
        select(User).where(User.school_id == school_id, User.role == "admin").order_by(User.id))
    if not owner:
        raise HTTPException(404, "Not found")
    pw = gen_password()
    owner.password_hash = hash_password(pw)
    db.commit()
    return {"username": owner.username, "temp_password": pw}
