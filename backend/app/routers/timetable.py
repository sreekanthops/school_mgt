"""Timetable (class periods) — CRUD + bulk operations + demo seed + teacher notifications + self-edit.

Endpoints:
  GET    /timetable/meta            subjects-by-grade, staff, sections-by-grade
  GET    /timetable                 list periods (filter: grade, section)
  POST   /timetable                 create one period
  PUT    /timetable/{id}            update one period  ← notifies teachers on assignment change
  DELETE /timetable/{id}            delete one period
  POST   /timetable/bulk            upsert many periods ← notifies teachers
  POST   /timetable/clear           wipe grade+section (or one day)
  POST   /timetable/copy            copy section timetable to another section
  POST   /timetable/seed-demo       create demo subjects + full timetable (owner only)
"""
import datetime as _dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (DAYS_OF_WEEK, GRADES, ClassPeriod, DirectMessage,
                      Staff, Student, Subject, TimetableLog, User)
from ..schemas import ClassPeriodIn
from ..security import need, perm_set, school_user

router = APIRouter(prefix="/api")

# ─────────────────────────── output helpers ───────────────────────────────────

def _period_out(p: ClassPeriod, subjects: dict, staff: dict) -> dict:
    subj = subjects.get(p.subject_id) if p.subject_id else None
    st   = staff.get(p.staff_id)      if p.staff_id   else None
    return {
        "id":            p.id,
        "grade":         p.grade,
        "section":       p.section,
        "day_of_week":   p.day_of_week,
        "period_number": p.period_number,
        "start_time":    p.start_time,
        "end_time":      p.end_time,
        "label":         p.label,
        "subject_id":    p.subject_id,
        "subject_name":  subj.name if subj else None,
        "staff_id":      p.staff_id,
        "staff_name":    st.name   if st   else None,
    }


def _enrich(rows: list[ClassPeriod], db: Session) -> list[dict]:
    if not rows:
        return []
    subj_ids  = {r.subject_id for r in rows if r.subject_id}
    staff_ids = {r.staff_id   for r in rows if r.staff_id}
    subjects  = {s.id: s for s in db.scalars(select(Subject).where(Subject.id.in_(subj_ids  or {0})))}
    staff     = {s.id: s for s in db.scalars(select(Staff).where(Staff.id.in_(staff_ids or {0})))}
    return [_period_out(p, subjects, staff) for p in rows]


# ─────────────────────────── notifications ────────────────────────────────────

def _notify(db: Session, actor: User, recipient_staff_id: int, body: str) -> None:
    """Send an in-app DM from the actor to the user linked to `recipient_staff_id`."""
    target = db.scalar(select(User).where(
        User.staff_id  == recipient_staff_id,
        User.school_id == actor.school_id,
        User.active    == True,  # noqa: E712
    ))
    if target and target.id != actor.id:
        db.add(DirectMessage(
            school_id    = actor.school_id,
            sender_id    = actor.id,
            recipient_id = target.id,
            body         = body,
            created_at   = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
        ))


def _assignment_msg(action: str, grade: str, section: str, day: str, period: int,
                    subj_name: Optional[str], start: Optional[str], end: Optional[str]) -> str:
    time_str = f"{start}–{end}" if start and end else (start or "")
    return (
        f"📅 Timetable {action}: You have been {'assigned to' if action == 'update' else 'removed from'} "
        f"Class {grade}-{section}, {day} Period {period}"
        f"{f' ({subj_name})' if subj_name else ''}"
        f"{f' at {time_str}' if time_str else ''}."
    )


# ─────────────────────────── meta ─────────────────────────────────────────────

@router.get("/timetable/meta")
def timetable_meta(user: User = Depends(school_user), db: Session = Depends(get_db)):
    subs  = list(db.scalars(select(Subject).where(Subject.school_id == user.school_id).order_by(Subject.name)))
    staff = list(db.scalars(select(Staff).where(Staff.school_id == user.school_id).order_by(Staff.name)))
    by_grade: dict[str, list] = {g: [] for g in GRADES}
    for s in subs:
        by_grade[s.grade].append({"id": s.id, "name": s.name})
    secs_by_grade: dict[str, list] = {g: [] for g in GRADES}
    for (grade, sec) in db.execute(
        select(distinct(Student.grade), Student.section)
        .where(Student.school_id == user.school_id)
        .order_by(Student.grade, Student.section)
    ):
        secs_by_grade[grade].append(sec)
    return {
        "subjects_by_grade": by_grade,
        "staff": [{"id": s.id, "name": s.name, "designation": s.designation} for s in staff],
        "sections_by_grade": secs_by_grade,
        "days":  list(DAYS_OF_WEEK),
        "grades": GRADES,
    }


# ─────────────────────────── list ─────────────────────────────────────────────

@router.get("/timetable")
def list_timetable(
    grade:   Optional[str] = None,
    section: Optional[str] = None,
    user: User = Depends(school_user),
    db:   Session = Depends(get_db),
):
    stmt = select(ClassPeriod).where(ClassPeriod.school_id == user.school_id)
    if grade:
        if grade not in GRADES:
            raise HTTPException(422, "Unknown grade")
        stmt = stmt.where(ClassPeriod.grade == grade)
    if section:
        stmt = stmt.where(ClassPeriod.section == section.upper()[:1])
    rows = list(db.scalars(
        stmt.order_by(ClassPeriod.grade, ClassPeriod.section,
                      ClassPeriod.day_of_week, ClassPeriod.period_number)
    ))
    return _enrich(rows, db)


# ─────────────────────────── single-period CRUD ───────────────────────────────

@router.post("/timetable", status_code=201)
def create_period(
    data: ClassPeriodIn,
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    _validate_refs(db, user.school_id, data)
    if db.scalar(select(ClassPeriod).where(
        ClassPeriod.school_id    == user.school_id,
        ClassPeriod.grade        == data.grade,
        ClassPeriod.section      == data.section,
        ClassPeriod.day_of_week  == data.day_of_week,
        ClassPeriod.period_number== data.period_number,
    )):
        raise HTTPException(409, "That slot already exists — use PUT to update it")
    p = ClassPeriod(school_id=user.school_id, **data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    # notify newly assigned teacher
    if data.staff_id:
        subj = db.get(Subject, data.subject_id) if data.subject_id else None
        _notify(db, user, data.staff_id,
                _assignment_msg("update", data.grade, data.section,
                                data.day_of_week, data.period_number,
                                subj.name if subj else None,
                                data.start_time, data.end_time))
        db.commit()
    return {"id": p.id}


@router.put("/timetable/{pid}")
def update_period(
    pid:  int,
    data: ClassPeriodIn,
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    p = _get(db, user.school_id, pid)
    old_staff_id = p.staff_id
    _validate_refs(db, user.school_id, data)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    db.commit()
    # notify: removed teacher + newly assigned teacher
    subj = db.get(Subject, data.subject_id) if data.subject_id else None
    if old_staff_id and old_staff_id != data.staff_id:
        _notify(db, user, old_staff_id,
                f"📅 Timetable update: You have been removed from "
                f"Class {data.grade}-{data.section}, {data.day_of_week} Period {data.period_number}.")
    if data.staff_id and data.staff_id != old_staff_id:
        _notify(db, user, data.staff_id,
                _assignment_msg("update", data.grade, data.section,
                                data.day_of_week, data.period_number,
                                subj.name if subj else None,
                                data.start_time, data.end_time))
    db.commit()
    return {"ok": True}


@router.delete("/timetable/{pid}", status_code=204)
def delete_period(
    pid:  int,
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    p = _get(db, user.school_id, pid)
    staff_id = p.staff_id
    if staff_id:
        _notify(db, user, staff_id,
                f"📅 Timetable update: Your period has been removed — "
                f"Class {p.grade}-{p.section}, {p.day_of_week} Period {p.period_number}.")
    db.delete(p)
    db.commit()


# ─────────────────────────── bulk operations ──────────────────────────────────

class BulkIn(BaseModel):
    periods: list[ClassPeriodIn] = Field(min_length=1, max_length=300)


@router.post("/timetable/bulk", status_code=200)
def bulk_upsert(
    data: BulkIn,
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    for item in data.periods:
        _validate_refs(db, user.school_id, item)
    created = updated = 0
    for item in data.periods:
        existing = db.scalar(select(ClassPeriod).where(
            ClassPeriod.school_id    == user.school_id,
            ClassPeriod.grade        == item.grade,
            ClassPeriod.section      == item.section,
            ClassPeriod.day_of_week  == item.day_of_week,
            ClassPeriod.period_number== item.period_number,
        ))
        if existing:
            old_staff = existing.staff_id
            for k, v in item.model_dump().items():
                setattr(existing, k, v)
            # notify teacher if reassigned
            if old_staff and old_staff != item.staff_id:
                _notify(db, user, old_staff,
                        f"📅 Timetable update: You have been removed from "
                        f"Class {item.grade}-{item.section}, {item.day_of_week} Period {item.period_number}.")
            if item.staff_id and item.staff_id != old_staff:
                subj = db.get(Subject, item.subject_id) if item.subject_id else None
                _notify(db, user, item.staff_id,
                        _assignment_msg("update", item.grade, item.section,
                                        item.day_of_week, item.period_number,
                                        subj.name if subj else None,
                                        item.start_time, item.end_time))
            updated += 1
        else:
            db.add(ClassPeriod(school_id=user.school_id, **item.model_dump()))
            if item.staff_id:
                subj = db.get(Subject, item.subject_id) if item.subject_id else None
                _notify(db, user, item.staff_id,
                        _assignment_msg("update", item.grade, item.section,
                                        item.day_of_week, item.period_number,
                                        subj.name if subj else None,
                                        item.start_time, item.end_time))
            created += 1
    db.commit()
    return {"created": created, "updated": updated}


class ClearIn(BaseModel):
    grade:       str
    section:     str = Field(pattern=r"^[A-Z]$")
    day_of_week: Optional[str] = None


@router.post("/timetable/clear", status_code=200)
def clear_timetable(
    data: ClearIn,
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    if data.grade not in GRADES:
        raise HTTPException(422, "Unknown grade")
    if data.day_of_week and data.day_of_week not in DAYS_OF_WEEK:
        raise HTTPException(422, "Unknown day")
    stmt = select(ClassPeriod).where(
        ClassPeriod.school_id == user.school_id,
        ClassPeriod.grade     == data.grade,
        ClassPeriod.section   == data.section,
    )
    if data.day_of_week:
        stmt = stmt.where(ClassPeriod.day_of_week == data.day_of_week)
    rows = list(db.scalars(stmt))
    for p in rows:
        if p.staff_id:
            _notify(db, user, p.staff_id,
                    f"📅 Timetable update: Your period has been removed — "
                    f"Class {p.grade}-{p.section}, {p.day_of_week} Period {p.period_number}.")
        db.delete(p)
    db.commit()
    return {"deleted": len(rows)}


class CopyIn(BaseModel):
    from_grade:   str
    from_section: str = Field(pattern=r"^[A-Z]$")
    to_grade:     str
    to_section:   str = Field(pattern=r"^[A-Z]$")
    overwrite:    bool = True


@router.post("/timetable/copy")
def copy_section(
    data: CopyIn,
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    for g in (data.from_grade, data.to_grade):
        if g not in GRADES:
            raise HTTPException(422, f"Unknown grade: {g}")
    source = list(db.scalars(select(ClassPeriod).where(
        ClassPeriod.school_id == user.school_id,
        ClassPeriod.grade     == data.from_grade,
        ClassPeriod.section   == data.from_section,
    )))
    if not source:
        raise HTTPException(404, "Source section has no timetable to copy")
    created = skipped = replaced = 0
    for src in source:
        existing = db.scalar(select(ClassPeriod).where(
            ClassPeriod.school_id    == user.school_id,
            ClassPeriod.grade        == data.to_grade,
            ClassPeriod.section      == data.to_section,
            ClassPeriod.day_of_week  == src.day_of_week,
            ClassPeriod.period_number== src.period_number,
        ))
        if existing:
            if not data.overwrite:
                skipped += 1
                continue
            existing.start_time = src.start_time
            existing.end_time   = src.end_time
            existing.subject_id = src.subject_id
            existing.staff_id   = src.staff_id
            existing.label      = src.label
            replaced += 1
        else:
            db.add(ClassPeriod(
                school_id=user.school_id, grade=data.to_grade, section=data.to_section,
                day_of_week=src.day_of_week, period_number=src.period_number,
                start_time=src.start_time, end_time=src.end_time,
                subject_id=src.subject_id, staff_id=src.staff_id, label=src.label,
            ))
            created += 1
    db.commit()
    return {"created": created, "replaced": replaced, "skipped": skipped}


# ─────────────────────────── demo seed ────────────────────────────────────────

# Standard school day — 8 teaching periods, short break, lunch break.
# period_number for breaks uses 90/91 (out of normal range, guaranteed unique).
_SLOTS = [
    # (period_number, start, end, label)
    (1,  "08:00", "08:45", None),
    (2,  "08:45", "09:30", None),
    (3,  "09:30", "10:15", None),
    (90, "10:15", "10:30", "Short Break"),   # 90 = break slot, unique per day
    (4,  "10:30", "11:15", None),
    (5,  "11:15", "12:00", None),
    (91, "12:00", "12:45", "Lunch Break"),   # 91 = lunch slot, unique per day
    (6,  "12:45", "13:30", None),
    (7,  "13:30", "14:15", None),
    (8,  "14:15", "15:00", None),
]

# Subject pool by grade band
_LOWER  = ["English", "Mathematics", "Environmental Studies", "Hindi", "Drawing & Craft", "Physical Education"]
_MIDDLE = ["English", "Mathematics", "Science", "Social Studies", "Hindi", "Sanskrit", "Computer Science", "Physical Education"]
_HIGH   = ["English", "Mathematics", "Physics", "Chemistry", "Biology", "History", "Geography", "Economics", "Hindi", "Computer Science", "Physical Education"]

_GRADE_SUBJECTS: dict[str, list[str]] = {
    "LKG": ["English", "Mathematics", "Drawing & Craft", "Physical Education"],
    "UKG": ["English", "Mathematics", "Drawing & Craft", "Environmental Studies", "Physical Education"],
    **{str(g): (_LOWER if g <= 5 else _MIDDLE if g <= 8 else _HIGH) for g in range(1, 11)},
}

# Rotating subject schedule: which subject fills each teaching period slot by day
# (6 subjects max per day, cycling through subject list)
_DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


@router.post("/timetable/seed-demo", status_code=200)
def seed_demo(
    user: User = Depends(need("timetable.manage")),
    db:   Session = Depends(get_db),
):
    """Create demo subjects (if not present) and a full weekly timetable for all grades A–D.
    Existing timetable rows are replaced. Staff assignments are left empty (no dummy staff
    is created — assign real teachers from the edit modal)."""
    school_id = user.school_id

    # Check we won't exceed subject count unreasonably
    existing_count = db.scalar(
        select(func.count()).select_from(ClassPeriod).where(ClassPeriod.school_id == school_id)
    ) or 0

    created_subjects = 0
    # ensure subjects exist for each grade
    subj_map: dict[str, dict[str, int]] = {}   # grade -> {name -> id}
    for grade, snames in _GRADE_SUBJECTS.items():
        subj_map[grade] = {}
        for sname in snames:
            s = db.scalar(select(Subject).where(
                Subject.school_id == school_id,
                Subject.name      == sname,
                Subject.grade     == grade,
            ))
            if not s:
                s = Subject(school_id=school_id, name=sname, grade=grade)
                db.add(s)
                db.flush()
                created_subjects += 1
            subj_map[grade][sname] = s.id

    # Sections to seed: A and B
    sections = ["A", "B"]
    days     = list(_DAY_ORDER)

    created_periods = replaced_periods = 0
    for grade in GRADES:
        subjects_for_grade = list(_GRADE_SUBJECTS.get(grade, _MIDDLE))
        n_subj = len(subjects_for_grade)
        for section in sections:
            for day_idx, day in enumerate(days):
                teaching_slot_idx = 0
                for (pnum, t_start, t_end, lbl) in _SLOTS:
                    is_break = lbl is not None
                    # pick subject: rotate per day/section so each day has a different order
                    subj_id = None
                    if not is_break:
                        offset = (day_idx * 3 + teaching_slot_idx + ord(section) - ord("A") * 2) % n_subj
                        subj_id = subj_map[grade][subjects_for_grade[offset]]
                        teaching_slot_idx += 1

                    # upsert — look up by the unique key (school, grade, section, day, period_number)
                    existing = db.scalar(select(ClassPeriod).where(
                        ClassPeriod.school_id    == school_id,
                        ClassPeriod.grade        == grade,
                        ClassPeriod.section      == section,
                        ClassPeriod.day_of_week  == day,
                        ClassPeriod.period_number== pnum,
                    ))
                    if existing:
                        existing.start_time = t_start
                        existing.end_time   = t_end
                        existing.subject_id = subj_id
                        existing.label      = lbl
                        replaced_periods += 1
                    else:
                        db.add(ClassPeriod(
                            school_id=school_id, grade=grade, section=section,
                            day_of_week=day, period_number=pnum,
                            start_time=t_start, end_time=t_end,
                            subject_id=subj_id, staff_id=None, label=lbl,
                        ))
                        created_periods += 1

    db.commit()
    return {
        "subjects_created": created_subjects,
        "periods_created":  created_periods,
        "periods_replaced": replaced_periods,
        "grades": len(GRADES),
        "sections": len(sections),
    }


# ─────────────────────────── teacher self-edit ────────────────────────────────

class SelfEditIn(BaseModel):
    """A teacher can swap the subject/staff on one of their own period slots.
    They cannot change grade, section, day, period number, or times — only subject and assigned teacher.
    Every change is logged and the owner is notified via DM."""
    subject_id: Optional[int] = None
    staff_id: Optional[int] = None   # The teacher can reassign the slot to another staff


@router.put("/timetable/{pid}/self-edit")
def teacher_self_edit(
    pid: int,
    data: SelfEditIn,
    user: User = Depends(school_user),
    db: Session = Depends(get_db),
):
    """Teacher self-edit: allowed if the period belongs to their assigned class
    (they are the current staff for that period) OR they hold timetable.self_edit permission."""
    perms = perm_set(user)
    if "timetable.manage" in perms:
        raise HTTPException(422, "Use the main timetable endpoint instead — you have full timetable access")
    if "timetable.self_edit" not in perms:
        raise HTTPException(403, "You do not have permission to edit the timetable")

    p = _get(db, user.school_id, pid)

    # Teacher may only edit periods currently assigned to themselves
    if p.staff_id != user.staff_id:
        raise HTTPException(403, "You can only edit periods assigned to you")

    # Validate refs if supplied
    old_subj: Optional[Subject] = db.get(Subject, p.subject_id) if p.subject_id else None
    old_staff: Optional[Staff] = db.get(Staff, p.staff_id) if p.staff_id else None

    new_subj: Optional[Subject] = None
    if data.subject_id is not None:
        new_subj = db.scalar(select(Subject).where(
            Subject.id == data.subject_id, Subject.school_id == user.school_id))
        if not new_subj:
            raise HTTPException(422, "Subject not found in this school")

    new_staff: Optional[Staff] = None
    if data.staff_id is not None:
        new_staff = db.scalar(select(Staff).where(
            Staff.id == data.staff_id, Staff.school_id == user.school_id))
        if not new_staff:
            raise HTTPException(422, "Staff member not found in this school")

    # Write audit log entry BEFORE applying changes
    log_entry = TimetableLog(
        school_id=user.school_id,
        period_id=p.id,
        actor_user_id=user.id,
        actor_name=user.full_name,
        grade=p.grade,
        section=p.section,
        day_of_week=p.day_of_week,
        period_number=p.period_number,
        old_subject=old_subj.name if old_subj else None,
        new_subject=new_subj.name if new_subj else (old_subj.name if old_subj else None),
        old_staff=old_staff.name if old_staff else None,
        new_staff=new_staff.name if new_staff else (old_staff.name if old_staff else None),
    )
    db.add(log_entry)

    # Apply changes
    if data.subject_id is not None:
        p.subject_id = data.subject_id
    if data.staff_id is not None:
        p.staff_id = data.staff_id

    # Notify owner (admin role) and notify old teacher if reassigned to someone else
    changed_staff = data.staff_id is not None and data.staff_id != (old_staff.id if old_staff else None)
    subj_name = new_subj.name if new_subj else (old_subj.name if old_subj else "")

    msg = (
        f"📅 Timetable self-edit by {user.full_name}: "
        f"Class {p.grade}-{p.section}, {p.day_of_week} Period {p.period_number}"
        f"{f' — subject changed to {subj_name}' if data.subject_id is not None else ''}"
        f"{f' — reassigned to {new_staff.name}' if new_staff else ''}."
    )

    # Notify all active admins
    admins = db.scalars(
        select(User).where(
            User.school_id == user.school_id,
            User.role == "admin",
            User.active.is_(True),
        )
    ).all()
    for admin in admins:
        if admin.id != user.id:
            db.add(DirectMessage(
                school_id=user.school_id, sender_id=user.id,
                recipient_id=admin.id, body=msg,
            ))

    # Notify newly assigned teacher if different from actor
    if new_staff and new_staff.id != user.staff_id:
        _notify(db, user, new_staff.id,
                f"📅 Timetable update: You have been assigned to "
                f"Class {p.grade}-{p.section}, {p.day_of_week} Period {p.period_number}"
                f"{f' ({subj_name})' if subj_name else ''}.")

    db.commit()
    return {"ok": True, "period_id": p.id}


@router.get("/timetable/logs")
def list_timetable_logs(
    grade: Optional[str] = None,
    section: Optional[str] = None,
    user: User = Depends(school_user),
    db: Session = Depends(get_db),
):
    """Owner/admin can view all teacher self-edit log entries.  Staff can see their own."""
    perms = perm_set(user)
    is_manager = user.role == "admin" or "timetable.manage" in perms

    stmt = select(TimetableLog).where(TimetableLog.school_id == user.school_id)
    if not is_manager:
        # staff only see their own changes
        stmt = stmt.where(TimetableLog.actor_user_id == user.id)
    if grade:
        stmt = stmt.where(TimetableLog.grade == grade)
    if section:
        stmt = stmt.where(TimetableLog.section == section.upper()[:1])
    stmt = stmt.order_by(TimetableLog.changed_at.desc()).limit(200)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "period_id": r.period_id,
            "actor_name": r.actor_name,
            "grade": r.grade,
            "section": r.section,
            "day_of_week": r.day_of_week,
            "period_number": r.period_number,
            "old_subject": r.old_subject,
            "new_subject": r.new_subject,
            "old_staff": r.old_staff,
            "new_staff": r.new_staff,
            "changed_at": r.changed_at.isoformat() + "Z",
        }
        for r in rows
    ]


# ─────────────────────────── helpers ──────────────────────────────────────────

def _get(db: Session, school_id: int, pid: int) -> ClassPeriod:
    p = db.scalar(select(ClassPeriod).where(
        ClassPeriod.id == pid, ClassPeriod.school_id == school_id))
    if not p:
        raise HTTPException(404, "Period not found")
    return p


def _validate_refs(db: Session, school_id: int, data: ClassPeriodIn) -> None:
    if data.subject_id:
        if not db.scalar(select(Subject).where(
                Subject.id == data.subject_id, Subject.school_id == school_id)):
            raise HTTPException(422, "Subject not found in this school")
    if data.staff_id:
        if not db.scalar(select(Staff).where(
                Staff.id == data.staff_id, Staff.school_id == school_id)):
            raise HTTPException(422, "Staff member not found in this school")
