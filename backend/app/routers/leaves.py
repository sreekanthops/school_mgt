"""Leave application system — staff and students.

Staff apply for leave (anyone with a linked staff profile).
Students apply for leave — routed to their section head (class_teacher_of staff for
their grade+section).  If no class teacher is set, the system picks the first staff
member who teaches that section in the timetable; as a final fallback it notifies all
admins.

Owner / users with 'leaves.manage' can approve or reject any leave.
The designated reviewer_user_id (section head) can also approve/reject student leaves.
Both sides receive a DirectMessage notification on review.
"""
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (ClassPeriod, DirectMessage, Staff, StaffLeave, Student,
                      User, LEAVE_TYPES, _utcnow)
from ..security import school_user

router = APIRouter(prefix="/api")
log = logging.getLogger("school.leaves")

STUDENT_LEAVE_TYPES = ("Sick", "Family", "Personal", "Other")


# ── helpers ───────────────────────────────────────────────────────────────────

def _notify(db: Session, school_id: int, sender_id: int, recipient_id: int, body: str) -> None:
    dm = DirectMessage(school_id=school_id, sender_id=sender_id,
                       recipient_id=recipient_id, body=body)
    db.add(dm)


def _leave_out(leave: StaffLeave, applicant_name: str | None = None,
               reviewer_name: str | None = None) -> dict:
    days = (leave.to_date - leave.from_date).days + 1
    return {
        "id": leave.id,
        "kind": "student" if leave.student_id else "staff",
        "staff_id": leave.staff_id,
        "student_id": leave.student_id,
        "applicant_name": applicant_name,
        "reviewer_user_id": leave.reviewer_user_id,
        "reviewer_name": reviewer_name,
        "from_date": leave.from_date.isoformat(),
        "to_date": leave.to_date.isoformat(),
        "days": days,
        "leave_type": leave.leave_type,
        "reason": leave.reason,
        "status": leave.status,
        "review_note": leave.review_note,
        "applied_at": leave.applied_at.isoformat() + "Z",
        "reviewed_at": (leave.reviewed_at.isoformat() + "Z") if leave.reviewed_at else None,
    }


def _section_head_user(db: Session, school_id: int,
                       grade: str, section: str) -> User | None:
    """Return the User account of the section head for a grade-section.

    Priority:
    1. Staff whose class_teacher_of == '<grade><section>' (e.g. '9A').
    2. First staff member who appears in the timetable for that section.
    3. None (caller falls back to admins).
    """
    key = f"{grade}{section}"
    # 1. class teacher
    ct = db.scalar(
        select(Staff).where(
            Staff.school_id == school_id,
            Staff.class_teacher_of == key,
        )
    )
    if ct:
        u = db.scalar(select(User).where(
            User.staff_id == ct.id,
            User.active.is_(True),
        ))
        if u:
            return u

    # 2. first teacher who teaches this section in the timetable
    period = db.scalar(
        select(ClassPeriod).where(
            ClassPeriod.school_id == school_id,
            ClassPeriod.grade == grade,
            ClassPeriod.section == section,
            ClassPeriod.staff_id.isnot(None),
            ClassPeriod.period_number < 90,
        ).order_by(ClassPeriod.period_number)
    )
    if period and period.staff_id:
        u = db.scalar(select(User).where(
            User.staff_id == period.staff_id,
            User.active.is_(True),
        ))
        if u:
            return u

    return None


# ── schemas ───────────────────────────────────────────────────────────────────

ALL_LEAVE_TYPES = tuple(set(LEAVE_TYPES) | set(STUDENT_LEAVE_TYPES))


class LeaveIn(BaseModel):
    from_date: dt.date
    to_date: dt.date
    leave_type: str = Field(default="Casual")
    reason: str | None = Field(default=None, max_length=500)


class ReviewIn(BaseModel):
    status: str
    review_note: str | None = Field(default=None, max_length=300)


# ── apply for leave ────────────────────────────────────────────────────────

@router.post("/leaves", status_code=201)
def apply_leave(data: LeaveIn, user: User = Depends(school_user),
                db: Session = Depends(get_db)):
    if data.to_date < data.from_date:
        raise HTTPException(422, "End date must be on or after start date")
    days = (data.to_date - data.from_date).days + 1
    if days > 60:
        raise HTTPException(422, "A single application cannot span more than 60 days")

    # ── STUDENT leave ──────────────────────────────────────────────────────
    if user.role == "student":
        if not user.student_id:
            raise HTTPException(403, "No student profile linked to this account")
        valid = tuple(set(LEAVE_TYPES) | set(STUDENT_LEAVE_TYPES))
        if data.leave_type not in valid:
            raise HTTPException(422, f"leave_type must be one of: {', '.join(sorted(valid))}")

        student = db.get(Student, user.student_id)
        if not student:
            raise HTTPException(403, "Student record not found")

        # Find section head
        reviewer = _section_head_user(db, user.school_id, student.grade, student.section)
        reviewer_user_id = reviewer.id if reviewer else None

        leave = StaffLeave(
            school_id=user.school_id,
            student_id=user.student_id,
            reviewer_user_id=reviewer_user_id,
            from_date=data.from_date,
            to_date=data.to_date,
            leave_type=data.leave_type,
            reason=data.reason,
        )
        db.add(leave)
        db.flush()

        applicant_name = student.name

        # Notify reviewer (section head) if found, else notify all admins
        notify_ids: list[int] = []
        if reviewer:
            notify_ids = [reviewer.id]
        else:
            notify_ids = [
                u.id for u in db.scalars(
                    select(User).where(
                        User.school_id == user.school_id,
                        User.active.is_(True),
                        User.role == "admin",
                    )
                )
            ]

        for uid in notify_ids:
            _notify(db, user.school_id, user.id, uid,
                    f"📋 Leave request from student {student.name} "
                    f"(Class {student.grade}-{student.section}): "
                    f"{data.leave_type} {data.from_date} – {data.to_date} "
                    f"({days} day{'s' if days != 1 else ''}). "
                    f"Reason: {data.reason or 'not specified'}")

        reviewer_obj = db.get(User, reviewer_user_id) if reviewer_user_id else None
        reviewer_name = reviewer_obj.full_name if reviewer_obj else None
        db.commit()
        log.info("student_leave_applied",
                 extra={"leave_id": leave.id, "student_id": user.student_id})
        return _leave_out(leave, applicant_name, reviewer_name)

    # ── STAFF leave ────────────────────────────────────────────────────────
    if not user.staff_id:
        raise HTTPException(403, "Only staff with a linked staff profile can apply for leave")
    if data.leave_type not in LEAVE_TYPES:
        raise HTTPException(422, f"leave_type must be one of: {', '.join(LEAVE_TYPES)}")

    leave = StaffLeave(
        school_id=user.school_id,
        staff_id=user.staff_id,
        from_date=data.from_date,
        to_date=data.to_date,
        leave_type=data.leave_type,
        reason=data.reason,
    )
    db.add(leave)
    db.flush()

    staff = db.get(Staff, user.staff_id)
    applicant_name = staff.name if staff else user.full_name

    managers = db.scalars(
        select(User).where(
            User.school_id == user.school_id,
            User.active.is_(True),
            User.id != user.id,
        )
    ).all()
    notify_ids = [
        u.id for u in managers
        if u.role == "admin" or "leaves.manage" in (u.permissions or "")
    ] or [u.id for u in managers if u.role == "admin"]

    for uid in notify_ids:
        _notify(db, user.school_id, user.id, uid,
                f"📋 Leave request from {applicant_name}: {data.leave_type} "
                f"{data.from_date} – {data.to_date} ({days} day{'s' if days != 1 else ''}). "
                f"Reason: {data.reason or 'not specified'}")

    db.commit()
    log.info("leave_applied", extra={"leave_id": leave.id, "staff_id": user.staff_id})
    return _leave_out(leave, applicant_name)


# ── list leaves ────────────────────────────────────────────────────────────

@router.get("/leaves")
def list_leaves(
    status: str | None = None,
    staff_id: int | None = None,
    student_id: int | None = None,
    user: User = Depends(school_user),
    db: Session = Depends(get_db),
):
    can_manage = (user.role == "admin"
                  or "leaves.manage" in (user.permissions or "")
                  or bool(user.staff_id))  # section heads see student leaves routed to them

    q = select(StaffLeave).where(StaffLeave.school_id == user.school_id)

    if user.role == "student":
        # Students only see their own
        if not user.student_id:
            return []
        q = q.where(StaffLeave.student_id == user.student_id)
    elif user.role == "admin" or "leaves.manage" in (user.permissions or ""):
        # Admin/HR: see all; filterable
        if staff_id:
            q = q.where(StaffLeave.staff_id == staff_id)
        if student_id:
            q = q.where(StaffLeave.student_id == student_id)
    else:
        # Regular staff: see own staff leaves + student leaves where they are the reviewer
        own_filter = StaffLeave.staff_id == user.staff_id if user.staff_id else None
        reviewer_filter = StaffLeave.reviewer_user_id == user.id

        from sqlalchemy import or_ as _or
        if own_filter is not None:
            q = q.where(_or(own_filter, reviewer_filter))
        else:
            q = q.where(reviewer_filter)

    if status:
        q = q.where(StaffLeave.status == status)
    q = q.order_by(StaffLeave.applied_at.desc())
    rows = db.scalars(q).all()

    # Bulk-fetch names
    sids = {r.staff_id for r in rows if r.staff_id}
    stids = {r.student_id for r in rows if r.student_id}
    ruids = {r.reviewer_user_id for r in rows if r.reviewer_user_id}

    staff_names: dict[int, str] = {}
    if sids:
        for sf in db.scalars(select(Staff).where(Staff.id.in_(sids))):
            staff_names[sf.id] = sf.name

    student_names: dict[int, str] = {}
    if stids:
        for st in db.scalars(select(Student).where(Student.id.in_(stids))):
            student_names[st.id] = st.name

    reviewer_names: dict[int, str] = {}
    if ruids:
        for ru in db.scalars(select(User).where(User.id.in_(ruids))):
            reviewer_names[ru.id] = ru.full_name

    def _name(r: StaffLeave) -> str | None:
        if r.staff_id:
            return staff_names.get(r.staff_id)
        return student_names.get(r.student_id)

    return [_leave_out(r, _name(r), reviewer_names.get(r.reviewer_user_id)) for r in rows]


@router.get("/leaves/{lid}")
def get_leave(lid: int, user: User = Depends(school_user),
              db: Session = Depends(get_db)):
    leave = db.get(StaffLeave, lid)
    if not leave or leave.school_id != user.school_id:
        raise HTTPException(404, "Not found")

    can_manage = user.role == "admin" or "leaves.manage" in (user.permissions or "")
    is_own_staff = leave.staff_id and leave.staff_id == user.staff_id
    is_own_student = leave.student_id and leave.student_id == user.student_id
    is_reviewer = leave.reviewer_user_id == user.id

    if not (can_manage or is_own_staff or is_own_student or is_reviewer):
        raise HTTPException(403, "Forbidden")

    staff = db.get(Staff, leave.staff_id) if leave.staff_id else None
    student = db.get(Student, leave.student_id) if leave.student_id else None
    reviewer = db.get(User, leave.reviewer_user_id) if leave.reviewer_user_id else None

    name = (staff.name if staff else None) or (student.name if student else None)
    return _leave_out(leave, name, reviewer.full_name if reviewer else None)


# ── review (approve / reject) ─────────────────────────────────────────────

@router.put("/leaves/{lid}/review", status_code=200)
def review_leave(lid: int, data: ReviewIn, user: User = Depends(school_user),
                 db: Session = Depends(get_db)):
    leave = db.get(StaffLeave, lid)
    if not leave or leave.school_id != user.school_id:
        raise HTTPException(404, "Not found")

    can_manage = user.role == "admin" or "leaves.manage" in (user.permissions or "")
    is_reviewer = leave.reviewer_user_id == user.id

    if not (can_manage or is_reviewer):
        raise HTTPException(403, "Only an admin, HR manager, or the assigned section head can review this leave")
    if leave.status != "pending":
        raise HTTPException(409, "Only pending leaves can be reviewed")
    if data.status not in ("approved", "rejected"):
        raise HTTPException(422, "status must be 'approved' or 'rejected'")

    leave.status = data.status
    leave.review_note = data.review_note
    leave.reviewed_by = user.id
    leave.reviewed_at = _utcnow()

    verb = "approved ✅" if data.status == "approved" else "rejected ❌"
    note_text = f" Note: {data.review_note}" if data.review_note else ""

    # Notify applicant
    if leave.staff_id:
        applicant_user = db.scalar(select(User).where(
            User.staff_id == leave.staff_id,
            User.school_id == user.school_id,
            User.active.is_(True),
        ))
        staff = db.get(Staff, leave.staff_id)
        name = staff.name if staff else "?"
    else:
        applicant_user = db.scalar(select(User).where(
            User.student_id == leave.student_id,
            User.school_id == user.school_id,
            User.active.is_(True),
        ))
        student = db.get(Student, leave.student_id) if leave.student_id else None
        name = student.name if student else "?"

    if applicant_user:
        _notify(db, user.school_id, user.id, applicant_user.id,
                f"Your leave request ({leave.leave_type} {leave.from_date} – {leave.to_date}) "
                f"has been {verb}.{note_text}")

    reviewer = db.get(User, leave.reviewer_user_id) if leave.reviewer_user_id else None
    db.commit()
    log.info("leave_reviewed",
             extra={"leave_id": lid, "status": data.status, "by": user.id})
    return _leave_out(leave, name, reviewer.full_name if reviewer else None)


# ── cancel / delete ────────────────────────────────────────────────────────

@router.delete("/leaves/{lid}", status_code=204)
def cancel_leave(lid: int, user: User = Depends(school_user),
                 db: Session = Depends(get_db)):
    leave = db.get(StaffLeave, lid)
    if not leave or leave.school_id != user.school_id:
        raise HTTPException(404, "Not found")

    can_manage = user.role == "admin" or "leaves.manage" in (user.permissions or "")
    is_own = (leave.staff_id and leave.staff_id == user.staff_id) or \
             (leave.student_id and leave.student_id == user.student_id)

    if not can_manage and not is_own:
        raise HTTPException(403, "Forbidden")
    if leave.status != "pending" and not can_manage:
        raise HTTPException(409, "Only pending applications can be cancelled")
    db.delete(leave)
    db.commit()
