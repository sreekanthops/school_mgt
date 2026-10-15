"""Superadmin console: schools, branches, plan limits, usage statistics, user controls and audit trail.

Every route here requires the superadmin role. Passwords are never logged or stored in the audit trail."""
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import analytics, storage
from ..config import CURRENT_YEAR
from ..db import get_db
from ..deps import make_code
from ..models import (GRADES, AuditLog, Branch, Chapter, Event, GalleryItem, Goal, School, Staff,
                      Student, Subject, User)
from ..schemas import YEAR, BranchIn, BranchStateIn, NewSchoolIn, SchoolAdminIn
from ..security import gen_password, hash_password, subscription_info, superadmin_only

router = APIRouter(prefix="/api")
log = logging.getLogger("school.platform")

NON_NULL = {"plan", "max_students", "max_staff"}  # an empty form value keeps the current setting


class ActiveIn(BaseModel):
    active: bool


# ---------- helpers ----------
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() + "Z" if d else None


def _school(db: Session, sid: int) -> School:
    s = db.get(School, sid)
    if not s:
        raise HTTPException(404, "Not found")
    return s


def audit(db: Session, actor: User, action: str, school: Optional[School], detail: Optional[str] = None) -> None:
    db.add(AuditLog(school_id=school.id if school else None, school_name=school.name if school else None,
                    actor=actor.username, action=action, detail=detail))


def _audit_out(a: AuditLog) -> dict:
    return {"id": a.id, "school_id": a.school_id, "school_name": a.school_name, "actor": a.actor,
            "action": a.action, "detail": a.detail, "at": _iso(a.created_at)}


def _grouped(db: Session, model, key=None) -> dict:
    col = key if key is not None else model.school_id
    return dict(db.execute(select(col, func.count()).select_from(model).group_by(col)).all())


def sub_status(end: Optional[date]) -> str:
    return subscription_info(end)["status"]


def _usage(used: int, limit: int) -> dict:
    return {"used": used, "max": limit, "pct": round(used * 100 / limit, 1) if limit else 0}


def _profile(s: School) -> dict:
    return {
        "id": s.id, "name": s.name, "city": s.city, "state": s.state, "board": s.board, "school_type": s.school_type,
        "email": s.email, "phone": s.phone, "website": s.website, "address": s.address, "founded": s.founded,
        "plan": s.plan, "max_students": s.max_students, "max_staff": s.max_staff,
        "subscription_end": s.subscription_end.isoformat() if s.subscription_end else None,
        "subscription_status": sub_status(s.subscription_end), "notes": s.notes,
        "subscription_days_left": subscription_info(s.subscription_end)["days_left"],
        "about": s.about, "mission": s.mission, "vision": s.vision, "contact": s.contact,
        "active": s.active, "created_at": s.created_at.isoformat(),
    }


def _owner(db: Session, sid: int) -> Optional[User]:
    return db.scalar(select(User).where(User.school_id == sid, User.role == "admin").order_by(User.id))


def _branch_out(b: Branch) -> dict:
    return {"id": b.id, "name": b.name, "city": b.city, "address": b.address, "phone": b.phone, "email": b.email,
            "principal": b.principal, "is_main": b.is_main, "active": b.active}


# ---------- overview ----------
@router.get("/platform/overview")
def overview(_: User = Depends(superadmin_only), db: Session = Depends(get_db), year: str = Query(CURRENT_YEAR, pattern=YEAR)):
    schools = db.scalars(select(School).order_by(School.id)).all()
    n_students, n_staff, n_users = _grouped(db, Student), _grouped(db, Staff), _grouped(db, User)
    rows, tot_fee, tot_paid = [], 0.0, 0.0
    for s in schools:
        overall = analytics.student_overall_map(db, s.id, year)
        fees = analytics.fee_pending_map(db, s.id, year)
        fee_total = sum(f["total"] for f in fees.values())
        fee_paid = sum(f["paid"] for f in fees.values())
        tot_fee, tot_paid = tot_fee + fee_total, tot_paid + fee_paid
        rows.append({
            "id": s.id, "name": s.name, "city": s.city, "plan": s.plan, "active": s.active,
            "students": n_students.get(s.id, 0), "staff": n_staff.get(s.id, 0), "users": n_users.get(s.id, 0),
            "avg_pct": round(sum(overall.values()) / len(overall), 1) if overall else None,
            "fee_total": round(fee_total, 2), "fee_paid": round(fee_paid, 2),
            "collection_pct": round(fee_paid * 100 / fee_total, 1) if fee_total else 0,
            "subscription_status": sub_status(s.subscription_end),
            "subscription_end": s.subscription_end.isoformat() if s.subscription_end else None,
            "student_usage": _usage(n_students.get(s.id, 0), s.max_students),
            "staff_usage": _usage(n_staff.get(s.id, 0), s.max_staff),
        })
    # cumulative schools by month (last 12)
    months, y, m = [], date.today().year, date.today().month
    for _i in range(12):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    created = Counter(s.created_at.strftime("%Y-%m") for s in schools)
    running = sum(c for k, c in created.items() if k < months[0])
    growth = []
    for k in months:
        running += created.get(k, 0)
        growth.append({"month": k, "schools": running})
    grade_counts = _grouped(db, Student, Student.grade)
    gender = dict(db.execute(select(Student.gender, func.count()).group_by(Student.gender)).all())
    attention = [
        {"id": r["id"], "name": r["name"], "reason": f"Subscription {r['subscription_status'].lower()}"}
        for r in rows if r["subscription_status"] in ("Expired", "Expiring")
    ] + [
        {"id": r["id"], "name": r["name"], "reason": f"{k.capitalize()} limit {r[f'{k}_usage']['pct']}% used"}
        for r in rows for k in ("student", "staff") if r[f"{k}_usage"]["pct"] >= 90
    ] + [{"id": r["id"], "name": r["name"], "reason": "School is disabled"} for r in rows if not r["active"]]
    return {
        "year": year,
        "totals": {
            "schools": len(schools), "active_schools": sum(1 for s in schools if s.active),
            "students": sum(n_students.values()), "staff": sum(n_staff.values()),
            "users": sum(n_users.values()), "branches": db.scalar(select(func.count()).select_from(Branch)),
            "fee_total": round(tot_fee, 2), "fee_paid": round(tot_paid, 2),
            "collection_pct": round(tot_paid * 100 / tot_fee, 1) if tot_fee else 0,
        },
        "schools": rows, "growth": growth,
        "plans": dict(Counter(s.plan for s in schools)),
        "grades": [{"grade": g, "students": grade_counts.get(g, 0)} for g in GRADES],
        "gender": gender, "attention": attention,
        "recent_activity": [_audit_out(a) for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(8))],
    }


# ---------- schools ----------
@router.get("/schools")
def list_schools(_: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    n_students, n_staff, n_users = _grouped(db, Student), _grouped(db, Staff), _grouped(db, User)
    n_branches = _grouped(db, Branch)
    last = dict(db.execute(select(User.school_id, func.max(User.last_login)).group_by(User.school_id)).all())
    owners: dict[int, User] = {}
    for u in db.scalars(select(User).where(User.role == "admin").order_by(User.id)):
        owners.setdefault(u.school_id, u)
    out = []
    for s in db.scalars(select(School).order_by(School.id)):
        o = owners.get(s.id)
        out.append({
            **_profile(s),
            "students": n_students.get(s.id, 0), "staff": n_staff.get(s.id, 0), "users": n_users.get(s.id, 0),
            "branches": n_branches.get(s.id, 0), "last_activity": _iso(last.get(s.id)),
            "student_usage": _usage(n_students.get(s.id, 0), s.max_students),
            "owner": {"id": o.id, "name": o.full_name, "username": o.username} if o else None,
        })
    return out


@router.post("/schools", status_code=201)
def create_school(data: NewSchoolIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    fields = {k: v for k, v in data.model_dump(exclude={"owner_name"}).items() if v is not None}
    school = School(**fields)
    db.add(school)
    db.flush()
    db.add(Branch(school_id=school.id, name="Main Campus", city=data.city, address=data.address,
                  phone=data.phone, email=data.email, is_main=True))
    pw = gen_password()
    owner = User(school_id=school.id, username=make_code(school.id, "o", 1), password_hash=hash_password(pw),
                 role="admin", full_name=data.owner_name)
    db.add(owner)
    audit(db, sa, "school_created", school, f"Owner login {owner.username}")
    db.commit()
    log.info("school_created", extra={"school_id": school.id, "by": sa.id})
    return {"school": {"id": school.id, "name": school.name},
            "owner": {"username": owner.username, "temp_password": pw}}


@router.get("/schools/{school_id}")
def school_detail(school_id: int, year: str = Query(CURRENT_YEAR, pattern=YEAR),
                  _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    count = lambda m: db.scalar(select(func.count()).select_from(m).where(m.school_id == s.id))
    dash = analytics.dashboard(db, s.id, year)
    n_students, n_staff = dash["total_students"], count(Staff)
    roles = dict(db.execute(select(User.role, func.count()).where(User.school_id == s.id).group_by(User.role)).all())
    week_ago = _now() - timedelta(days=7)
    owner = _owner(db, s.id)
    people = db.scalars(select(User).where(User.school_id == s.id, User.role.in_(["admin", "staff"]))
                        .order_by(User.role, User.username)).all()
    last = db.scalar(select(func.max(User.last_login)).where(User.school_id == s.id))
    return {
        **_profile(s), "year": year,
        "owner": {"id": owner.id, "name": owner.full_name, "username": owner.username,
                  "last_login": _iso(owner.last_login), "active": owner.active} if owner else None,
        "counts": {
            "students": n_students, "staff": n_staff, "users": sum(roles.values()),
            "subjects": count(Subject), "chapters": db.scalar(
                select(func.count()).select_from(Chapter).join(Subject, Subject.id == Chapter.subject_id)
                .where(Subject.school_id == s.id)),
            "events": count(Event), "gallery": count(GalleryItem), "goals": count(Goal), "branches": count(Branch),
        },
        "roles": roles, "last_activity": _iso(last),
        "active_users_7d": db.scalar(select(func.count()).select_from(User).where(
            User.school_id == s.id, User.last_login >= week_ago)),
        "usage": {"students": _usage(n_students, s.max_students), "staff": _usage(n_staff, s.max_staff)},
        "gender": dict(db.execute(select(Student.gender, func.count()).where(Student.school_id == s.id)
                                  .group_by(Student.gender)).all()),
        "by_grade": dash["by_grade"], "distribution": dash["distribution"], "avg_pct": dash["avg_pct"],
        "fees": dash["fees"], "top_students": dash["top_students"], "at_risk": dash["at_risk"],
        "staff_by_department": [{"department": d, "count": c} for d, c in db.execute(
            select(Staff.department, func.count()).where(Staff.school_id == s.id)
            .group_by(Staff.department).order_by(func.count().desc())).all()],
        "branches": [_branch_out(b) for b in db.scalars(
            select(Branch).where(Branch.school_id == s.id).order_by(Branch.is_main.desc(), Branch.name))],
        "people": [{"id": u.id, "username": u.username, "name": u.full_name, "role": u.role, "active": u.active,
                    "last_login": _iso(u.last_login)} for u in people],
        "audit": [_audit_out(a) for a in db.scalars(
            select(AuditLog).where(AuditLog.school_id == s.id).order_by(AuditLog.id.desc()).limit(15))],
    }


@router.put("/schools/{school_id}")
def update_school(school_id: int, data: SchoolAdminIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    changed = []
    for k, v in data.model_dump().items():
        if v is None and k in NON_NULL:
            continue
        if getattr(s, k) != v:
            setattr(s, k, v)
            changed.append(k)
    if changed:
        audit(db, sa, "school_updated", s, "Changed: " + ", ".join(changed))
    db.commit()
    return _profile(s)


@router.put("/schools/{school_id}/active")
def set_school_active(school_id: int, body: ActiveIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    s.active = body.active
    audit(db, sa, "school_enabled" if s.active else "school_disabled", s)
    db.commit()
    return {"id": s.id, "active": s.active}


@router.delete("/schools/{school_id}", status_code=204)
def delete_school(school_id: int, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    audit(db, sa, "school_deleted", s, "All data removed")
    db.delete(s)
    db.commit()
    storage.remove_school(school_id)


# ---------- owner / user controls ----------
@router.post("/schools/{school_id}/owner/reset-password")
def reset_owner_password(school_id: int, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    owner = _owner(db, school_id)
    if not owner:
        raise HTTPException(404, "Not found")
    pw = gen_password()
    owner.password_hash = hash_password(pw)
    owner.must_change = True
    audit(db, sa, "owner_password_reset", s, owner.username)
    db.commit()
    return {"username": owner.username, "temp_password": pw}


def _school_user(db: Session, school_id: int, uid: int) -> User:
    u = db.get(User, uid)
    if not u or u.school_id != school_id or u.role == "superadmin":
        raise HTTPException(404, "Not found")
    return u


@router.put("/schools/{school_id}/users/{uid}/active")
def set_user_active(school_id: int, uid: int, body: ActiveIn, sa: User = Depends(superadmin_only),
                    db: Session = Depends(get_db)):
    s, u = _school(db, school_id), _school_user(db, school_id, uid)
    u.active = body.active
    audit(db, sa, "user_enabled" if u.active else "user_disabled", s, u.username)
    db.commit()
    return {"id": u.id, "active": u.active}


@router.post("/schools/{school_id}/users/{uid}/reset-password")
def reset_user_password(school_id: int, uid: int, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s, u = _school(db, school_id), _school_user(db, school_id, uid)
    pw = gen_password()
    u.password_hash = hash_password(pw)
    u.must_change = True
    audit(db, sa, "user_password_reset", s, u.username)
    db.commit()
    return {"username": u.username, "temp_password": pw}


# ---------- branches ----------
def _branch(db: Session, school_id: int, bid: int) -> Branch:
    b = db.get(Branch, bid)
    if not b or b.school_id != school_id:
        raise HTTPException(404, "Not found")
    return b


@router.get("/schools/{school_id}/branches")
def list_branches(school_id: int, _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    _school(db, school_id)
    return [_branch_out(b) for b in db.scalars(
        select(Branch).where(Branch.school_id == school_id).order_by(Branch.is_main.desc(), Branch.name))]


@router.post("/schools/{school_id}/branches", status_code=201)
def add_branch(school_id: int, data: BranchIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    first = not db.scalar(select(func.count()).select_from(Branch).where(Branch.school_id == school_id))
    b = Branch(school_id=school_id, is_main=first, **data.model_dump())
    db.add(b)
    audit(db, sa, "branch_added", s, data.name)
    db.commit()
    return _branch_out(b)


@router.put("/schools/{school_id}/branches/{bid}")
def update_branch(school_id: int, bid: int, data: BranchIn, sa: User = Depends(superadmin_only),
                  db: Session = Depends(get_db)):
    s, b = _school(db, school_id), _branch(db, school_id, bid)
    for k, v in data.model_dump().items():
        setattr(b, k, v)
    audit(db, sa, "branch_updated", s, b.name)
    db.commit()
    return _branch_out(b)


@router.put("/schools/{school_id}/branches/{bid}/state")
def set_branch_state(school_id: int, bid: int, data: BranchStateIn, sa: User = Depends(superadmin_only),
                     db: Session = Depends(get_db)):
    s, b = _school(db, school_id), _branch(db, school_id, bid)
    if data.is_main is False:
        raise HTTPException(422, "Make another branch the main branch instead")
    if data.is_main:
        if not b.active and data.active is not True:
            raise HTTPException(422, "A disabled branch cannot be the main branch")
        for other in db.scalars(select(Branch).where(Branch.school_id == school_id, Branch.id != b.id)):
            other.is_main = False
        b.is_main, b.active = True, True
    if data.active is not None:
        if data.active is False and b.is_main:
            raise HTTPException(422, "The main branch cannot be disabled")
        b.active = data.active
    audit(db, sa, "branch_updated", s, f"{b.name}: main={b.is_main}, active={b.active}")
    db.commit()
    return _branch_out(b)


@router.delete("/schools/{school_id}/branches/{bid}", status_code=204)
def delete_branch(school_id: int, bid: int, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s, b = _school(db, school_id), _branch(db, school_id, bid)
    if b.is_main:
        raise HTTPException(422, "The main branch cannot be deleted")
    audit(db, sa, "branch_deleted", s, b.name)
    db.delete(b)
    db.commit()


# ---------- audit trail ----------
@router.get("/audit")
def audit_trail(school_id: Optional[int] = None, limit: int = Query(50, ge=1, le=200),
                _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if school_id is not None:
        stmt = stmt.where(AuditLog.school_id == school_id)
    return [_audit_out(a) for a in db.scalars(stmt)]
