"""Staff leave application system.

Staff apply for leave (anyone with a linked staff profile).
Owner / users with 'leaves.manage' permission can approve or reject.
Both sides receive a DirectMessage notification on review.
"""
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DirectMessage, School, Staff, StaffLeave, User, LEAVE_TYPES, _utcnow
from ..security import current_user, need, school_user

router = APIRouter(prefix="/api")
log = logging.getLogger("school.leaves")


# ── helpers ───────────────────────────────────────────────────────────────────

def _notify(db: Session, school_id: int, sender_id: int, recipient_id: int, body: str) -> None:
    """Send an in-app DM notification."""
    dm = DirectMessage(school_id=school_id, sender_id=sender_id, recipient_id=recipient_id, body=body)
    db.add(dm)


def _leave_out(leave: StaffLeave, staff_name: str | None = None) -> dict:
    days = (leave.to_date - leave.from_date).days + 1
    return {
        "id": leave.id,
        "staff_id": leave.staff_id,
        "staff_name": staff_name,
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


# ── schemas ───────────────────────────────────────────────────────────────────

class LeaveIn(BaseModel):
    from_date: dt.date
    to_date: dt.date
    leave_type: str = Field(default="Casual")
    reason: str | None = Field(default=None, max_length=500)


class ReviewIn(BaseModel):
    status: str        # "approved" | "rejected"
    review_note: str | None = Field(default=None, max_length=300)


# ── staff: apply for leave ─────────────────────────────────────────────────

@router.post("/leaves", status_code=201)
def apply_leave(data: LeaveIn, user: User = Depends(school_user), db: Session = Depends(get_db)):
    """Any staff member (or admin) with a linked staff profile can apply for leave."""
    if not user.staff_id:
        raise HTTPException(403, "Only staff with a linked staff profile can apply for leave")
    if data.to_date < data.from_date:
        raise HTTPException(422, "End date must be on or after start date")
    if data.leave_type not in LEAVE_TYPES:
        raise HTTPException(422, f"leave_type must be one of: {', '.join(LEAVE_TYPES)}")
    days = (data.to_date - data.from_date).days + 1
    if days > 60:
        raise HTTPException(422, "A single application cannot span more than 60 days")

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

    # Notify admins/HR who hold leaves.manage (or all admins if none found)
    staff = db.get(Staff, user.staff_id)
    staff_name = staff.name if staff else user.full_name
    managers = db.scalars(
        select(User).where(
            User.school_id == user.school_id,
            User.active == True,  # noqa: E712
            User.id != user.id,
        )
    ).all()
    notify_ids = [
        u.id for u in managers
        if u.role == "admin" or "leaves.manage" in (u.permissions or "")
    ]
    if not notify_ids:
        notify_ids = [u.id for u in managers if u.role == "admin"]

    for uid in notify_ids:
        _notify(db, user.school_id, user.id, uid,
                f"📋 Leave request from {staff_name}: {data.leave_type} "
                f"{data.from_date} – {data.to_date} ({days} day{'s' if days != 1 else ''}). "
                f"Reason: {data.reason or 'not specified'}")
    db.commit()
    log.info("leave_applied", extra={"leave_id": leave.id, "staff_id": user.staff_id})
    return _leave_out(leave, staff_name)


# ── list leaves ────────────────────────────────────────────────────────────

@router.get("/leaves")
def list_leaves(
    status: str | None = None,
    staff_id: int | None = None,
    user: User = Depends(school_user),
    db: Session = Depends(get_db),
):
    """
    Admin / leaves.manage: see all leaves (filterable by status and staff).
    Staff: see only their own leaves.
    """
    from_school = user.role == "admin" or "leaves.manage" in (user.permissions or "")
    q = select(StaffLeave).where(StaffLeave.school_id == user.school_id)
    if not from_school:
        # staff can only see their own
        if not user.staff_id:
            return []
        q = q.where(StaffLeave.staff_id == user.staff_id)
    else:
        if staff_id:
            q = q.where(StaffLeave.staff_id == staff_id)
    if status:
        q = q.where(StaffLeave.status == status)
    q = q.order_by(StaffLeave.applied_at.desc())
    rows = db.scalars(q).all()

    # Fetch staff names in bulk
    staff_ids = {r.staff_id for r in rows}
    names = {}
    if staff_ids:
        for sf in db.scalars(select(Staff).where(Staff.id.in_(staff_ids))):
            names[sf.id] = sf.name

    return [_leave_out(r, names.get(r.staff_id)) for r in rows]


@router.get("/leaves/{lid}")
def get_leave(lid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    leave = db.get(StaffLeave, lid)
    if not leave or leave.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    can_manage = user.role == "admin" or "leaves.manage" in (user.permissions or "")
    is_own = leave.staff_id == user.staff_id
    if not can_manage and not is_own:
        raise HTTPException(403, "Forbidden")
    staff = db.get(Staff, leave.staff_id)
    return _leave_out(leave, staff.name if staff else None)


# ── admin: review ──────────────────────────────────────────────────────────

@router.put("/leaves/{lid}/review", status_code=200)
def review_leave(
    lid: int,
    data: ReviewIn,
    user: User = Depends(need("leaves.manage")),
    db: Session = Depends(get_db),
):
    """Approve or reject a pending leave application."""
    leave = db.get(StaffLeave, lid)
    if not leave or leave.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    if leave.status != "pending":
        raise HTTPException(409, "Only pending leaves can be reviewed")
    if data.status not in ("approved", "rejected"):
        raise HTTPException(422, "status must be 'approved' or 'rejected'")

    leave.status = data.status
    leave.review_note = data.review_note
    leave.reviewed_by = user.id
    leave.reviewed_at = _utcnow()

    # Notify the staff member
    staff = db.get(Staff, leave.staff_id)
    # Find the User account linked to this staff member
    staff_user = db.scalar(select(User).where(
        User.staff_id == leave.staff_id,
        User.school_id == user.school_id,
        User.active == True,  # noqa: E712
    ))
    if staff_user:
        verb = "approved ✅" if data.status == "approved" else "rejected ❌"
        note_text = f" Note: {data.review_note}" if data.review_note else ""
        _notify(db, user.school_id, user.id, staff_user.id,
                f"Your leave request ({leave.leave_type} {leave.from_date} – {leave.to_date}) "
                f"has been {verb}.{note_text}")

    db.commit()
    log.info("leave_reviewed", extra={"leave_id": lid, "status": data.status, "by": user.id})
    return _leave_out(leave, staff.name if staff else None)


# ── staff: cancel own pending leave ───────────────────────────────────────

@router.delete("/leaves/{lid}", status_code=204)
def cancel_leave(lid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    """A staff member can withdraw their own pending application."""
    leave = db.get(StaffLeave, lid)
    if not leave or leave.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    can_manage = user.role == "admin" or "leaves.manage" in (user.permissions or "")
    is_own = leave.staff_id == user.staff_id
    if not can_manage and not is_own:
        raise HTTPException(403, "Forbidden")
    if leave.status != "pending" and not can_manage:
        raise HTTPException(409, "Only pending applications can be cancelled")
    db.delete(leave)
    db.commit()
