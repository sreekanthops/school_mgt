"""School holiday calendar.

Admin / holidays.manage — add, edit, delete holidays.
All school members — read-only view.
"""
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Holiday
from ..security import need, school_user
from ..models import User

router = APIRouter(prefix="/api")
log = logging.getLogger("school.holidays")

CATEGORIES = ("national", "regional", "school")


# ── schemas ───────────────────────────────────────────────────────────────────

class HolidayIn(BaseModel):
    date: dt.date
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    category: str = Field(default="school")


# ── helpers ───────────────────────────────────────────────────────────────────

def _out(h: Holiday) -> dict:
    return {
        "id": h.id,
        "date": h.date.isoformat(),
        "name": h.name,
        "description": h.description,
        "category": h.category,
    }


# ── read (all school members) ─────────────────────────────────────────────

@router.get("/holidays")
def list_holidays(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(school_user),
    db: Session = Depends(get_db),
):
    q = select(Holiday).where(Holiday.school_id == user.school_id)
    if year:
        from sqlalchemy import extract
        q = q.where(extract("year", Holiday.date) == year)
    if month:
        from sqlalchemy import extract as ext2
        q = q.where(ext2("month", Holiday.date) == month)
    q = q.order_by(Holiday.date)
    return [_out(h) for h in db.scalars(q)]


@router.get("/holidays/upcoming")
def upcoming_holidays(
    days: int = 7,
    user: User = Depends(school_user),
    db: Session = Depends(get_db),
):
    """Return holidays in the next `days` days (used by the dashboard banner)."""
    today = dt.date.today()
    until = today + dt.timedelta(days=days)
    rows = db.scalars(
        select(Holiday).where(
            Holiday.school_id == user.school_id,
            Holiday.date >= today,
            Holiday.date <= until,
        ).order_by(Holiday.date)
    ).all()
    return [_out(h) for h in rows]


# ── write (holidays.manage or admin) ─────────────────────────────────────

@router.post("/holidays", status_code=201)
def create_holiday(
    data: HolidayIn,
    user: User = Depends(need("holidays.manage")),
    db: Session = Depends(get_db),
):
    if data.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of: {', '.join(CATEGORIES)}")
    h = Holiday(
        school_id=user.school_id,
        date=data.date,
        name=data.name.strip(),
        description=data.description,
        category=data.category,
    )
    db.add(h)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "A holiday already exists on that date")
    log.info("holiday_created", extra={"holiday_id": h.id, "school_id": user.school_id})
    return _out(h)


@router.put("/holidays/{hid}")
def update_holiday(
    hid: int,
    data: HolidayIn,
    user: User = Depends(need("holidays.manage")),
    db: Session = Depends(get_db),
):
    h = db.get(Holiday, hid)
    if not h or h.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    if data.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of: {', '.join(CATEGORIES)}")
    h.date = data.date
    h.name = data.name.strip()
    h.description = data.description
    h.category = data.category
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "A holiday already exists on that date")
    return _out(h)


@router.delete("/holidays/{hid}", status_code=204)
def delete_holiday(
    hid: int,
    user: User = Depends(need("holidays.manage")),
    db: Session = Depends(get_db),
):
    h = db.get(Holiday, hid)
    if not h or h.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    db.delete(h)
    db.commit()
