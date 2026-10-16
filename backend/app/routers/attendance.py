"""Daily attendance: marking, reports and low-attendance alerts.

Present (P) and Late (L) both count as attended; Absent (A) does not. Percentages are over the days that were
actually recorded for that student.

Timetable enforcement: when a staff member saves an attendance sheet the system checks whether there is a
timetable assignment for that grade/section/day. If the slot is assigned to a *different* staff member
the save still succeeds (substitute teacher case) but in-app DirectMessages are sent to:
  - the school owner (admin role)
  - every admin-level user in the school
  - the originally-assigned teacher (if their User record exists)
"""
import datetime as _dt
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_student
from ..models import (ATTENDANCE_STATUS, DAYS_OF_WEEK, GRADES, Attendance, ClassPeriod, DirectMessage,
                      Staff, Student, User)
from ..reports import csv_response
from ..security import need, perm_set, school_user

router = APIRouter(prefix="/api")

LOW_PCT = 75.0          # below this attendance is flagged
WINDOW_DAYS = 30        # alerts look at the last 30 days
MIN_DAYS = 5            # ...and need at least this many recorded days before judging
STREAK = 3              # this many absent days in a row is flagged too
MAX_RANGE = 366


class Entry(BaseModel):
    student_id: int
    status: str

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v not in ATTENDANCE_STATUS:
            raise ValueError("status must be P, A or L")
        return v


class SheetIn(BaseModel):
    grade: str
    section: str = Field(pattern=r"^[A-Z]$")
    day: date
    entries: list[Entry] = Field(max_length=300)

    @field_validator("grade")
    @classmethod
    def _g(cls, v):
        if v not in GRADES:
            raise ValueError("invalid class")
        return v


def _class_students(db: Session, school_id: int, grade: str, section: str) -> list[Student]:
    if grade not in GRADES:
        raise HTTPException(422, "Unknown class")
    return list(db.scalars(select(Student).where(Student.school_id == school_id, Student.grade == grade,
                                                  Student.section == section.upper()[:1]).order_by(Student.name)))


def _check_day(day: date) -> None:
    if day > date.today():
        raise HTTPException(422, "You cannot mark attendance for a future date")
    if (date.today() - day).days > 90:
        raise HTTPException(422, "Attendance older than 90 days cannot be changed")


@router.get("/attendance/sheet")
def sheet(grade: str, section: str = Query(max_length=2), day: Optional[date] = None,
          user: User = Depends(need("attendance.manage")), db: Session = Depends(get_db)):
    day = day or date.today()
    studs = _class_students(db, user.school_id, grade, section)
    got = {a.student_id: a.status for a in db.scalars(select(Attendance).where(
        Attendance.school_id == user.school_id, Attendance.day == day,
        Attendance.student_id.in_([s.id for s in studs] or [0])))}
    return {"day": day.isoformat(), "grade": grade, "section": section.upper()[:1], "marked": bool(got),
            "students": [{"id": s.id, "name": s.name, "admission_no": s.admission_no, "status": got.get(s.id)} for s in studs]}


@router.put("/attendance/sheet")
def save_sheet(data: SheetIn, user: User = Depends(need("attendance.manage")), db: Session = Depends(get_db)):
    _check_day(data.day)
    allowed = {s.id for s in _class_students(db, user.school_id, data.grade, data.section)}
    if any(e.student_id not in allowed for e in data.entries):
        raise HTTPException(422, "Every student must belong to that class")
    existing = {a.student_id: a for a in db.scalars(select(Attendance).where(
        Attendance.school_id == user.school_id, Attendance.day == data.day, Attendance.student_id.in_(allowed or {0})))}
    for e in data.entries:
        row = existing.get(e.student_id)
        if row:
            row.status, row.marked_by = e.status, user.username
        else:
            db.add(Attendance(school_id=user.school_id, student_id=e.student_id, day=data.day, status=e.status,
                              marked_by=user.username))
    db.commit()
    # Timetable check: notify if a substitute is marking attendance
    if user.role == "staff":
        _check_substitute(db, user, data.grade, data.section, data.day)
    return {"saved": len(data.entries)}


# ---------- timetable enforcement helpers ----------

def _day_abbr(d: date) -> str:
    """Convert a date to a DAYS_OF_WEEK abbreviation."""
    return DAYS_OF_WEEK[d.weekday()] if d.weekday() < len(DAYS_OF_WEEK) else ""


def _check_substitute(db: Session, marker: User, grade: str, section: str, day: date) -> None:
    """If any timetable slot for this grade/section/day is assigned to a different staff member,
    send DM notifications to all admin users and the assigned teacher."""
    day_abbr = _day_abbr(day)
    if not day_abbr:
        return  # Sunday — no timetable
    # Find all periods for this grade/section/day that have a staff assignment
    periods = list(db.scalars(select(ClassPeriod).where(
        ClassPeriod.school_id == marker.school_id,
        ClassPeriod.grade == grade,
        ClassPeriod.section == section,
        ClassPeriod.day_of_week == day_abbr,
        ClassPeriod.staff_id.is_not(None),
    )))
    if not periods:
        return
    # Find the staff record for the marker
    marker_staff_id: Optional[int] = marker.staff_id
    # Collect assigned staff IDs that differ from the marker
    substitute_slots = [p for p in periods if p.staff_id != marker_staff_id]
    if not substitute_slots:
        return
    # The marker is acting as a substitute — notify
    assigned_staff_ids = {p.staff_id for p in substitute_slots}
    # Build notification message
    assigned_names = []
    assigned_user_ids = []
    for sid in assigned_staff_ids:
        st = db.get(Staff, sid)
        if st:
            assigned_names.append(st.name)
        # Find User record linked to this staff
        u = db.scalar(select(User).where(User.staff_id == sid, User.school_id == marker.school_id))
        if u:
            assigned_user_ids.append(u.id)
    msg_body = (
        f"Substitute attendance alert: {marker.full_name} marked attendance for "
        f"Class {grade}-{section} on {day.isoformat()} (day: {day_abbr}). "
        f"The scheduled teacher(s) were: {', '.join(assigned_names) or 'unknown'}."
    )
    # Find all admin users in the school + the assigned teachers
    admins = list(db.scalars(select(User).where(
        User.school_id == marker.school_id,
        User.role == "admin",
        User.active == True,  # noqa: E712
    )))
    notify_ids = {u.id for u in admins} | set(assigned_user_ids)
    notify_ids.discard(marker.id)  # don't message yourself
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    for rid in notify_ids:
        db.add(DirectMessage(
            school_id=marker.school_id,
            sender_id=marker.id,
            recipient_id=rid,
            body=msg_body,
            created_at=now,
        ))
    if notify_ids:
        db.commit()


def _summary(rows: list[tuple[date, str]]) -> dict:
    p = sum(1 for _, s in rows if s == "P")
    l = sum(1 for _, s in rows if s == "L")
    a = sum(1 for _, s in rows if s == "A")
    n = p + l + a
    return {"present": p, "late": l, "absent": a, "days": n, "pct": round((p + l) * 100 / n, 1) if n else None}


def _absent_streak(rows: list[tuple[date, str]]) -> int:
    """Consecutive absent recorded days, counted back from the latest recorded day."""
    run = 0
    for _, s in sorted(rows, reverse=True):
        if s != "A":
            break
        run += 1
    return run


def low_attendance(db: Session, school_id: int, today: Optional[date] = None) -> list[dict]:
    """Students under LOW_PCT over the last WINDOW_DAYS (once MIN_DAYS are recorded), or absent STREAK days running."""
    today = today or date.today()
    start = today - timedelta(days=WINDOW_DAYS)
    by: dict[int, list] = defaultdict(list)
    for a in db.scalars(select(Attendance).where(Attendance.school_id == school_id, Attendance.day >= start,
                                                  Attendance.day <= today)):
        by[a.student_id].append((a.day, a.status))
    if not by:
        return []
    studs = {s.id: s for s in db.scalars(select(Student).where(Student.id.in_(list(by))))}
    out = []
    for sid, rows in by.items():
        sm, streak = _summary(rows), _absent_streak(rows)
        low = sm["days"] >= MIN_DAYS and sm["pct"] < LOW_PCT
        if not (low or streak >= STREAK) or sid not in studs:
            continue
        s = studs[sid]
        out.append({"id": s.id, "name": s.name, "grade": s.grade, "section": s.section, "admission_no": s.admission_no,
                    "pct": sm["pct"], "absent": sm["absent"], "days": sm["days"], "streak": streak,
                    "reason": "low" if low else "streak"})
    return sorted(out, key=lambda r: (r["pct"] is None, r["pct"] if r["pct"] is not None else 0))


@router.get("/attendance/alerts")
def alerts(user: User = Depends(need("attendance.manage", "students.view")), db: Session = Depends(get_db)):
    return {"threshold": LOW_PCT, "window_days": WINDOW_DAYS, "items": low_attendance(db, user.school_id)}


def _range(frm: Optional[date], to: Optional[date]) -> tuple[date, date]:
    to = to or date.today()
    frm = frm or to - timedelta(days=29)
    if frm > to:
        raise HTTPException(422, "Start date is after the end date")
    if (to - frm).days > MAX_RANGE:
        raise HTTPException(422, "Choose a range of at most one year")
    return frm, to


def _report(db: Session, school_id: int, grade: Optional[str], section: Optional[str], frm: date, to: date) -> dict:
    stmt = select(Student).where(Student.school_id == school_id)
    if grade:
        if grade not in GRADES:
            raise HTTPException(422, "Unknown class")
        stmt = stmt.where(Student.grade == grade)
    if section:
        stmt = stmt.where(Student.section == section.upper()[:1])
    studs = list(db.scalars(stmt.order_by(Student.grade, Student.section, Student.name)))
    ids = [s.id for s in studs]
    by: dict[int, list] = defaultdict(list)
    daily: dict[date, list[str]] = defaultdict(list)
    for a in db.scalars(select(Attendance).where(Attendance.school_id == school_id, Attendance.day >= frm,
                                                  Attendance.day <= to, Attendance.student_id.in_(ids or [0]))):
        by[a.student_id].append((a.day, a.status))
        daily[a.day].append(a.status)
    items = [{"id": s.id, "name": s.name, "admission_no": s.admission_no, "grade": s.grade, "section": s.section,
              **_summary(by.get(s.id, [])), "low": (lambda m: m["days"] >= MIN_DAYS and m["pct"] < LOW_PCT)(_summary(by.get(s.id, [])))}
             for s in studs]
    trend = [{"day": d.isoformat(), "pct": round(sum(1 for x in v if x != "A") * 100 / len(v), 1), "absent": v.count("A")}
             for d, v in sorted(daily.items())]
    allrows = [r for v in by.values() for r in v]
    return {"from": frm.isoformat(), "to": to.isoformat(), "threshold": LOW_PCT, "overall": _summary(allrows),
            "items": items, "trend": trend}


@router.get("/attendance/report")
def report(grade: Optional[str] = None, section: Optional[str] = Query(None, max_length=2),
           frm: Optional[date] = Query(None, alias="from"), to: Optional[date] = None,
           user: User = Depends(need("attendance.manage", "students.view")), db: Session = Depends(get_db)):
    frm, to = _range(frm, to)
    return _report(db, user.school_id, grade, section, frm, to)


@router.get("/export/attendance")
def export_attendance(grade: Optional[str] = None, section: Optional[str] = Query(None, max_length=2),
                      frm: Optional[date] = Query(None, alias="from"), to: Optional[date] = None,
                      user: User = Depends(need("attendance.manage", "students.view")), db: Session = Depends(get_db)):
    frm, to = _range(frm, to)
    r = _report(db, user.school_id, grade, section, frm, to)
    return csv_response(["Student ID", "Name", "Class", "Present", "Late", "Absent", "Days recorded", "Attendance %"],
                        [[i["admission_no"], i["name"], f"{i['grade']}-{i['section']}", i["present"], i["late"], i["absent"],
                          i["days"], i["pct"]] for i in r["items"]], f"attendance-{frm}-{to}")


@router.get("/students/{sid}/attendance")
def student_attendance(sid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    own = user.role == "student" and user.student_id == sid
    if not (own or perm_set(user) & {"students.view", "attendance.manage"}):
        raise HTTPException(403, "You can only view your own details")
    rows = [(a.day, a.status) for a in db.scalars(select(Attendance).where(
        Attendance.student_id == s.id, Attendance.day >= date.today() - timedelta(days=MAX_RANGE)).order_by(Attendance.day))]
    month = [r for r in rows if r[0] >= date.today() - timedelta(days=WINDOW_DAYS)]
    months: dict[str, list] = defaultdict(list)
    for r in rows:
        months[r[0].strftime("%Y-%m")].append(r)
    sm = _summary(month)
    return {"month": sm, "year": _summary(rows), "low": sm["days"] >= MIN_DAYS and sm["pct"] < LOW_PCT,
            "threshold": LOW_PCT, "streak": _absent_streak(rows),
            "by_month": [{"month": m, **_summary(v)} for m, v in sorted(months.items())],
            "recent": [{"day": d.isoformat(), "status": st} for d, st in rows[-14:]][::-1]}
