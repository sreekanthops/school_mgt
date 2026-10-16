"""Students, marks, fees, staff and photos."""
import secrets
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Integer, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import analytics, storage
from ..db import get_db
from ..deps import can_see_fees, can_see_student, get_owned, get_student, next_code, staff_letter, year_of
from ..models import (EXAM_MAX, Announcement, Attendance, Chapter, ClassPeriod, DirectMessage,
                      Event, Fee, GalleryItem, Goal, Holiday, Mark,
                      Payment, School, Staff, StaffLeave, Student, Subject, User)
from . import attendance
from ..schemas import FeeIn, MarkIn, PaymentIn, StaffIn, StudentIn
from ..security import (PRINCIPAL_DEFAULT, TEACHER_DEFAULT, gen_password, hash_password, need, perm_set, school_user,
                        staff_side)

router = APIRouter(prefix="/api")

STUDENT_FIELDS = ["id", "admission_no", "name", "gender", "dob", "grade", "section", "guardian_name",
                  "phone", "email", "address", "blood_group"]


def _student_out(s: Student) -> dict:
    d = {k: getattr(s, k) for k in STUDENT_FIELDS}
    d["dob"] = s.dob.isoformat()
    d["has_photo"] = bool(s.photo)
    d["photo_v"] = storage.version(s.photo)
    return d


def _staff_out(s: Staff) -> dict:
    return {
        "id": s.id, "employee_id": s.employee_id, "name": s.name, "gender": s.gender,
        "designation": s.designation, "department": s.department, "qualification": s.qualification,
        "experience_years": s.experience_years, "subjects": s.subjects, "class_teacher_of": s.class_teacher_of,
        "phone": s.phone, "email": s.email, "joined_on": s.joined_on.isoformat(), "bio": s.bio,
        "has_photo": bool(s.photo), "photo_v": storage.version(s.photo),
    }


def _check_limit(db: Session, school_id: int, model, limit_attr: str, label: str) -> None:
    """The plan limit the platform team set for this school."""
    limit = getattr(db.get(School, school_id), limit_attr)
    if db.scalar(select(func.count()).select_from(model).where(model.school_id == school_id)) >= limit:
        raise HTTPException(403, f"Your plan allows at most {limit} {label} records. Contact the platform team to raise it.")


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(year: Optional[str] = None, user: User = Depends(staff_side), db: Session = Depends(get_db)):
    sid = user.school_id
    perms = perm_set(user)
    year = year_of(db, sid, year)
    d = analytics.dashboard(db, sid, year)
    count = lambda m: db.scalar(select(func.count()).select_from(m).where(m.school_id == sid))
    d["counts"] = {
        "students": d["total_students"], "staff": count(Staff), "subjects": count(Subject),
        "chapters": db.scalar(select(func.count()).select_from(Chapter).join(Subject, Subject.id == Chapter.subject_id)
                              .where(Subject.school_id == sid)),
        "events": count(Event), "gallery": count(GalleryItem), "goals": count(Goal),
    }
    d["upcoming_events"] = [
        {"id": e.id, "title": e.title, "date": e.date.isoformat(), "category": e.category}
        for e in db.scalars(select(Event).where(Event.school_id == sid, Event.date >= date.today())
                            .order_by(Event.date).limit(4))
    ]
    d["attendance_alerts"] = attendance.low_attendance(db, sid)[:5] if perms & {"attendance.manage", "students.view"} else []
    if "students.view" not in perms:
        d.update(top_students=[], at_risk=[], avg_pct=None, distribution={}, by_grade=[])
    if not ({"fees.view", "fees.manage"} & perms):
        d["fees"] = None
        d["top_defaulters"] = []
        for g in d["by_grade"]:
            g["pending_fee"] = None
    return d


# ---------- staff personal dashboard ----------

@router.get("/staff/me/dashboard")
def staff_dashboard(year: Optional[str] = None,
                    user: User = Depends(school_user),
                    db: Session = Depends(get_db)):
    """Personal dashboard for the signed-in staff member.
    Returns today's schedule, full week schedule, subjects taught with mark stats,
    pending leave count, recent announcements, upcoming holidays and unread message count.
    """
    if user.role not in ("staff",):
        raise HTTPException(403, "This endpoint is for staff members only")
    if not user.staff_id:
        raise HTTPException(403, "No staff profile linked to this account")

    staff = db.get(Staff, user.staff_id)
    if not staff:
        raise HTTPException(404, "Staff profile not found")

    year = year_of(db, user.school_id, year)
    today_name = date.today().strftime("%a")[:3]  # Mon / Tue / ...

    # ── timetable: all periods assigned to this teacher ───────────────────────
    periods = db.scalars(
        select(ClassPeriod)
        .where(ClassPeriod.school_id == user.school_id,
               ClassPeriod.staff_id == user.staff_id,
               ClassPeriod.period_number < 90)
        .order_by(ClassPeriod.day_of_week, ClassPeriod.period_number)
    ).all()

    subj_ids = {p.subject_id for p in periods if p.subject_id}
    subj_map: dict[int, Subject] = ({s.id: s for s in db.scalars(
        select(Subject).where(Subject.id.in_(subj_ids)))} if subj_ids else {})

    DAYS_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    def _period_out(p: ClassPeriod) -> dict:
        subj = subj_map.get(p.subject_id) if p.subject_id else None
        return {
            "id": p.id,
            "grade": p.grade,
            "section": p.section,
            "day_of_week": p.day_of_week,
            "period_number": p.period_number,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "subject_id": p.subject_id,
            "subject_name": subj.name if subj else None,
        }

    today_periods = [_period_out(p) for p in periods if p.day_of_week == today_name]
    week_by_day: dict[str, list] = {d: [] for d in DAYS_ORDER}
    for p in periods:
        if p.day_of_week in week_by_day:
            week_by_day[p.day_of_week].append(_period_out(p))

    # ── subjects taught: resolve from staff.subjects field ────────────────────
    subject_names = [n.strip() for n in (staff.subjects or "").split(",") if n.strip()]
    taught_subjects = list(db.scalars(
        select(Subject).where(
            Subject.school_id == user.school_id,
            Subject.name.in_(subject_names),
        ).order_by(Subject.grade, Subject.name)
    )) if subject_names else []

    # ── mark stats per taught subject: avg, top, count, weak ─────────────────
    subject_stats = []
    for subj in taught_subjects:
        rows = db.execute(
            select(Mark.student_id,
                   func.avg(Mark.score * 100.0 / Mark.max_score).label("avg_pct"),
                   func.count().label("entries"))
            .where(Mark.subject_id == subj.id, Mark.academic_year == year)
            .group_by(Mark.student_id)
        ).all()
        if not rows:
            subject_stats.append({
                "id": subj.id, "name": subj.name, "grade": subj.grade,
                "student_count": 0, "avg_pct": None, "top_pct": None,
                "weak_count": 0, "strong_count": 0,
            })
            continue
        scores = [r.avg_pct for r in rows if r.avg_pct is not None]
        weak   = sum(1 for s in scores if s < 50)
        strong = sum(1 for s in scores if s >= 85)
        subject_stats.append({
            "id": subj.id,
            "name": subj.name,
            "grade": subj.grade,
            "student_count": len(rows),
            "avg_pct": round(sum(scores) / len(scores), 1) if scores else None,
            "top_pct":  round(max(scores), 1) if scores else None,
            "weak_count": weak,
            "strong_count": strong,
        })

    # ── also gather per-section classes taught from timetable ─────────────────
    sections_taught = sorted({
        (p.grade, p.section) for p in periods
    }, key=lambda x: (x[0], x[1]))
    classes_taught = [{"grade": g, "section": s} for g, s in sections_taught]

    # ── pending leaves for this staff member ─────────────────────────────────
    pending_leaves = db.scalar(
        select(func.count()).select_from(StaffLeave)
        .where(StaffLeave.staff_id == user.staff_id,
               StaffLeave.status == "pending")
    ) or 0

    # student leaves assigned to this teacher as reviewer ─────────────────────
    reviewer_pending = db.scalar(
        select(func.count()).select_from(StaffLeave)
        .where(StaffLeave.reviewer_user_id == user.id,
               StaffLeave.status == "pending")
    ) or 0

    # ── unread messages ───────────────────────────────────────────────────────
    unread_messages = db.scalar(
        select(func.count()).select_from(DirectMessage)
        .where(DirectMessage.recipient_id == user.id,
               DirectMessage.read.is_(False),
               DirectMessage.hidden_recipient.is_(False))
    ) or 0

    # ── recent announcements (last 5 visible to this role) ────────────────────
    ann_rows = db.scalars(
        select(Announcement)
        .where(Announcement.school_id == user.school_id,
               Announcement.audience.in_(["all", "staff"]))
        .order_by(Announcement.created_at.desc())
        .limit(5)
    ).all()
    announcements = [
        {"id": a.id, "title": a.title, "body": a.body[:200],
         "created_at": a.created_at.isoformat() + "Z", "pinned": a.pinned}
        for a in ann_rows
    ]

    # ── upcoming holidays (next 30 days) ─────────────────────────────────────
    today = date.today()
    upcoming_holidays = [
        {"id": h.id, "date": h.date.isoformat(), "name": h.name, "category": h.category}
        for h in db.scalars(
            select(Holiday)
            .where(Holiday.school_id == user.school_id,
                   Holiday.date >= today)
            .order_by(Holiday.date)
            .limit(5)
        )
    ]

    # ── recent approved leaves history (last 5) ───────────────────────────────
    recent_leaves = []
    for leave in db.scalars(
        select(StaffLeave)
        .where(StaffLeave.staff_id == user.staff_id)
        .order_by(StaffLeave.applied_at.desc())
        .limit(5)
    ):
        days = (leave.to_date - leave.from_date).days + 1
        recent_leaves.append({
            "id": leave.id,
            "from_date": leave.from_date.isoformat(),
            "to_date": leave.to_date.isoformat(),
            "leave_type": leave.leave_type,
            "status": leave.status,
            "days": days,
        })

    return {
        "staff": {
            "id": staff.id,
            "name": staff.name,
            "designation": staff.designation,
            "department": staff.department,
            "employee_id": staff.employee_id,
            "class_teacher_of": staff.class_teacher_of,
            "has_photo": bool(staff.photo),
            "photo_v": storage.version(staff.photo),
        },
        "year": year,
        "today": today_name,
        "today_periods": today_periods,
        "week_schedule": week_by_day,
        "classes_taught": classes_taught,
        "subject_stats": subject_stats,
        "pending_leaves": pending_leaves,
        "reviewer_pending": reviewer_pending,
        "recent_leaves": recent_leaves,
        "unread_messages": unread_messages,
        "announcements": announcements,
        "upcoming_holidays": upcoming_holidays,
    }


# ---------- attendance badge helper ----------

def _att_pct_map(db: Session, school_id: int, student_ids: list[int]) -> dict[int, float | None]:
    """Return attendance percentage (0-100, rounded) for the given student IDs for the current year.
    Students with no records get None."""
    if not student_ids:
        return {}
    rows = db.execute(
        select(Attendance.student_id,
               func.count().label("total"),
               func.sum(case((Attendance.status == "P", 1), else_=0)).label("present"))
        .where(
            Attendance.school_id == school_id,
            Attendance.student_id.in_(student_ids),
        )
        .group_by(Attendance.student_id)
    ).all()
    result: dict[int, float | None] = {sid: None for sid in student_ids}
    for sid, total, present in rows:
        if total and total > 0:
            result[sid] = round((present / total) * 100, 1)
    return result


# ---------- students ----------
@router.get("/students")
def list_students(
    q: Optional[str] = Query(None, max_length=100), grade: Optional[str] = None,
    section: Optional[str] = Query(None, max_length=2), page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100), year: Optional[str] = None,
    user: User = Depends(school_user), db: Session = Depends(get_db),
):
    perms = perm_set(user)
    year = year_of(db, user.school_id, year)
    full = "students.view" in perms
    fee_ok = bool({"fees.view", "fees.manage"} & perms)
    stmt = select(Student).where(Student.school_id == user.school_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Student.name.ilike(like), Student.admission_no.ilike(like)))
    if grade:
        stmt = stmt.where(Student.grade == grade)
    if section:
        stmt = stmt.where(Student.section == section)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Student.grade, Student.section, Student.name)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    overall = analytics.student_overall_map(db, user.school_id, year) if full else {}
    fees = analytics.fee_pending_map(db, user.school_id, year) if fee_ok else {}
    att_pct = _att_pct_map(db, user.school_id, [s.id for s in rows]) if full else {}
    items = []
    for s in rows:
        row = {"id": s.id, "name": s.name, "grade": s.grade, "section": s.section,
               "has_photo": bool(s.photo), "photo_v": storage.version(s.photo)}
        if full:  # classmates/others only get the basic directory view above
            row.update(admission_no=s.admission_no, gender=s.gender, guardian_name=s.guardian_name, phone=s.phone,
                       overall_pct=overall.get(s.id),
                       letter=analytics.grade_letter(overall[s.id]) if s.id in overall else None,
                       att_pct=att_pct.get(s.id))
        if fee_ok:
            row["fee_pending"] = round(fees[s.id]["pending"], 2) if s.id in fees else 0
        items.append(row)
    return {"items": items, "total": total, "page": page, "page_size": page_size, "detailed": full}


@router.post("/students", status_code=201)
def add_student(data: StudentIn, user: User = Depends(need("students.manage")), db: Session = Depends(get_db)):
    """Creates the student with an auto-generated ID and a login (ID + one-time temporary password)."""
    _check_limit(db, user.school_id, Student, "max_students", "student")
    fields = data.model_dump(exclude={"admission_no"})
    for _ in range(3):  # retry if two requests grab the same roll number
        code = next_code(db, user.school_id, "s", data.grade)
        s = Student(school_id=user.school_id, admission_no=code, **fields)
        db.add(s)
        db.flush()
        pw = gen_password()
        db.add(User(school_id=user.school_id, username=code, password_hash=hash_password(pw), role="student",
                    full_name=s.name, student_id=s.id))
        try:
            db.commit()
            return {**_student_out(s), "login": {"username": code, "temp_password": pw}}
        except IntegrityError:
            db.rollback()
    raise HTTPException(409, "Could not allocate a student ID, please try again")


@router.put("/students/{sid}")
def update_student(sid: int, data: StudentIn, user: User = Depends(need("students.manage")),
                   db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    for k, v in data.model_dump(exclude={"admission_no"}).items():  # the student ID never changes
        setattr(s, k, v)
    db.commit()
    return _student_out(s)


@router.delete("/students/{sid}", status_code=204)
def delete_student(sid: int, user: User = Depends(need("students.manage")), db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    storage.remove(s.photo)
    storage.remove(s.pending_photo)
    db.delete(s)
    db.commit()


@router.get("/students/{sid}")
def student_detail(sid: int, year: Optional[str] = None, user: User = Depends(school_user),
                   db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    if not can_see_student(user, sid):
        raise HTTPException(403, "You can only view your own details")
    current = year_of(db, user.school_id)
    year = year or current
    years = set(analytics.student_years(db, sid)) | {current}
    years = sorted(years, reverse=True)
    perf = analytics.performance(db, s, year)
    history = []
    for y in sorted(years):
        p = analytics.performance(db, s, y)
        if p["has_data"]:
            history.append({"year": y, "grade": p["grade"], "overall_pct": p["overall_pct"]})
    perms = perm_set(user)
    return {
        "student": _student_out(s), "years": years, "selected_year": year, "performance": perf,
        "history": history, "rank": analytics.class_rank(db, s, year) if perf["has_data"] else None,
        "fees": analytics.fee_summary(db, sid, year) if can_see_fees(user, sid) else None,
        "photo_pending": bool(s.pending_photo) if (user.student_id == sid or "photos.approve" in perms) else False,
        "can": {"edit": "students.manage" in perms, "marks": "marks.edit" in perms,
                "fees": "fees.manage" in perms, "photo_request": user.student_id == sid,
                "approve": "photos.approve" in perms},
    }


@router.get("/subjects-for-marks")
def subjects_for_marks(sid: int, year: Optional[str] = None, user: User = Depends(need("marks.edit")),
                       db: Session = Depends(get_db)):
    """Subjects of the student's class, plus their existing marks, for the marks-entry form."""
    s = get_student(db, user, sid)
    subs = db.scalars(select(Subject).where(Subject.school_id == user.school_id, Subject.grade == s.grade)
                      .order_by(Subject.name)).all()
    return [{"id": x.id, "name": x.name} for x in subs]


@router.post("/students/{sid}/marks", status_code=201)
def upsert_mark(sid: int, data: MarkIn, user: User = Depends(need("marks.edit")), db: Session = Depends(get_db)):
    get_student(db, user, sid)
    get_owned(db, Subject, data.subject_id, user.school_id)
    mx = EXAM_MAX[data.exam]
    if data.score > mx:
        raise HTTPException(422, f"Score cannot exceed {mx}")
    m = db.scalar(select(Mark).where(Mark.student_id == sid, Mark.subject_id == data.subject_id,
                                     Mark.exam == data.exam, Mark.academic_year == data.academic_year))
    if m:
        m.score = data.score
    else:
        db.add(Mark(student_id=sid, subject_id=data.subject_id, exam=data.exam,
                    academic_year=data.academic_year, score=data.score, max_score=mx))
    db.commit()
    return {"ok": True}


# ---------- fees ----------
def _fee_guard(user: User, sid: int):
    if not can_see_fees(user, sid):
        raise HTTPException(403, "You do not have access to fee details")


@router.get("/fees")
def fees_overview(year: Optional[str] = None, grade: Optional[str] = None, status: Optional[str] = Query(None, max_length=20),
                  q: Optional[str] = Query(None, max_length=100),
                  user: User = Depends(need("fees.view", "fees.manage")), db: Session = Depends(get_db)):
    """School-wide fee register (one row per student)."""
    year = year_of(db, user.school_id, year)
    stmt = select(Student).where(Student.school_id == user.school_id)
    if grade:
        stmt = stmt.where(Student.grade == grade)
    if q:
        stmt = stmt.where(or_(Student.name.ilike(f"%{q}%"), Student.admission_no.ilike(f"%{q}%")))
    fm = analytics.fee_pending_map(db, user.school_id, year)
    items = []
    for s in db.scalars(stmt.order_by(Student.grade, Student.section, Student.name)):
        f = fm.get(s.id)
        total, paid = (f["total"], f["paid"]) if f else (0.0, 0.0)
        pending = max(total - paid, 0.0)
        st = "No fee set" if not f else "Paid" if pending <= 0 else "Partial" if paid > 0 else "Unpaid"
        if status and st != status:
            continue
        items.append({"id": s.id, "name": s.name, "grade": s.grade, "section": s.section, "admission_no": s.admission_no,
                      "total": total, "paid": paid, "pending": pending, "status": st})
    total = sum(i["total"] for i in items)
    paid = sum(i["paid"] for i in items)
    return {"year": year, "items": items,
            "summary": {"total": total, "paid": paid, "pending": max(total - paid, 0.0),
                        "collection_pct": round(paid * 100 / total, 1) if total else 0}}


@router.get("/students/{sid}/fees")
def student_fees(sid: int, year: Optional[str] = None, user: User = Depends(school_user), db: Session = Depends(get_db)):
    get_student(db, user, sid)
    _fee_guard(user, sid)
    return analytics.fee_summary(db, sid, year_of(db, user.school_id, year))


@router.put("/students/{sid}/fees")
def set_fee(sid: int, data: FeeIn, user: User = Depends(need("fees.manage")), db: Session = Depends(get_db)):
    get_student(db, user, sid)
    f = db.scalar(select(Fee).where(Fee.student_id == sid, Fee.academic_year == data.academic_year))
    if f:
        f.total_amount = data.total_amount
    else:
        db.add(Fee(student_id=sid, academic_year=data.academic_year, total_amount=data.total_amount))
    db.commit()
    return analytics.fee_summary(db, sid, data.academic_year)


@router.post("/students/{sid}/payments", status_code=201)
def add_payment(sid: int, data: PaymentIn, user: User = Depends(need("fees.manage")), db: Session = Depends(get_db)):
    get_student(db, user, sid)
    summary = analytics.fee_summary(db, sid, data.academic_year)
    if summary["status"] == "No fee set":
        raise HTTPException(422, "No fee has been set for this year")
    if data.amount > summary["pending"]:
        raise HTTPException(422, f"Amount exceeds pending balance of {summary['pending']}")
    db.add(Payment(student_id=sid, academic_year=data.academic_year, amount=data.amount, paid_on=date.today(),
                   mode=data.mode, receipt_no=f"RCPT-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"))
    db.commit()
    return analytics.fee_summary(db, sid, data.academic_year)


# ---------- student photos (student requests, admin approves) ----------
@router.get("/students/{sid}/photo")
def student_photo(sid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    return storage.serve(get_student(db, user, sid).photo)


@router.get("/students/{sid}/pending-photo")
def student_pending_photo(sid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    if not (user.student_id == sid or "photos.approve" in perm_set(user)):
        raise HTTPException(403, "Not allowed")
    return storage.serve(s.pending_photo)


@router.post("/students/{sid}/photo", status_code=204)
async def set_student_photo(sid: int, request: Request, user: User = Depends(need("students.manage")),
                            db: Session = Depends(get_db)):
    """Staff with students.manage set the photo directly."""
    s = get_student(db, user, sid)
    data, ext = await storage.read_image(request)
    old = s.photo
    s.photo = storage.save(user.school_id, data, ext)
    db.commit()
    storage.remove(old)


@router.post("/students/{sid}/photo-request", status_code=204)
async def request_photo(sid: int, request: Request, user: User = Depends(school_user),
                        db: Session = Depends(get_db)):
    """A student can only submit a request for their own photo; it is not shown until approved."""
    if user.role != "student" or user.student_id != sid:
        raise HTTPException(403, "You can only request a change to your own photo")
    s = get_student(db, user, sid)
    data, ext = await storage.read_image(request)
    old = s.pending_photo
    s.pending_photo = storage.save(user.school_id, data, ext)
    db.commit()
    storage.remove(old)


@router.get("/photo-requests")
def photo_requests(user: User = Depends(need("photos.approve")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Student).where(Student.school_id == user.school_id, Student.pending_photo.is_not(None))
                      .order_by(Student.name)).all()
    return [{"student_id": s.id, "name": s.name, "grade": s.grade, "section": s.section,
             "has_current": bool(s.photo), "photo_v": storage.version(s.photo)} for s in rows]


@router.post("/students/{sid}/photo-request/approve", status_code=204)
def approve_photo(sid: int, user: User = Depends(need("photos.approve")), db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    if not s.pending_photo:
        raise HTTPException(404, "No pending request")
    old = s.photo
    s.photo, s.pending_photo = s.pending_photo, None
    db.commit()
    storage.remove(old)


@router.post("/students/{sid}/photo-request/reject", status_code=204)
def reject_photo(sid: int, user: User = Depends(need("photos.approve")), db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    storage.remove(s.pending_photo)
    s.pending_photo = None
    db.commit()


# ---------- staff ----------
def _staff_basic(s: Staff) -> dict:
    """Short view: what everyone in the school can see at a glance."""
    return {"id": s.id, "name": s.name, "designation": s.designation, "department": s.department,
            "subjects": s.subjects, "class_teacher_of": s.class_teacher_of,
            "has_photo": bool(s.photo), "photo_v": storage.version(s.photo)}


@router.get("/staff")
def list_staff(q: Optional[str] = Query(None, max_length=100), department: Optional[str] = None,
               user: User = Depends(school_user), db: Session = Depends(get_db)):
    stmt = select(Staff).where(Staff.school_id == user.school_id).order_by(Staff.name)
    if q:
        stmt = stmt.where(or_(Staff.name.ilike(f"%{q}%"), Staff.subjects.ilike(f"%{q}%")))
    if department:
        stmt = stmt.where(Staff.department == department)
    return [_staff_basic(r) for r in db.scalars(stmt)]


@router.get("/staff/{sid}")
def staff_detail(sid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    s = get_owned(db, Staff, sid, user.school_id)
    perms = perm_set(user)
    out = _staff_out(s)
    out["can"] = {"edit": "staff.manage" in perms,
                  "photo": "staff.manage" in perms or user.staff_id == s.id}
    # subjects they teach, resolved to the school's subject records
    names = [p.strip() for p in (s.subjects or "").split(",") if p.strip()]
    out["teaches"] = [{"id": x.id, "name": x.name, "grade": x.grade} for x in db.scalars(
        select(Subject).where(Subject.school_id == user.school_id, Subject.name.in_(names))
        .order_by(Subject.grade, Subject.name))] if names else []
    # timetable schedule for this staff member
    periods = db.scalars(
        select(ClassPeriod).where(ClassPeriod.school_id == user.school_id,
                                  ClassPeriod.staff_id == sid)
        .order_by(ClassPeriod.day_of_week, ClassPeriod.period_number)
    ).all()
    subj_ids = {p.subject_id for p in periods if p.subject_id}
    subj_map: dict[int, Subject] = {x.id: x for x in db.scalars(
        select(Subject).where(Subject.id.in_(subj_ids)))} if subj_ids else {}
    out["schedule"] = [
        {
            "id": p.id,
            "grade": p.grade,
            "section": p.section,
            "day_of_week": p.day_of_week,
            "period_number": p.period_number,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "subject": ({"id": subj_map[p.subject_id].id, "name": subj_map[p.subject_id].name}
                        if p.subject_id and p.subject_id in subj_map else None),
            "label": p.label,
        }
        for p in periods
        if p.period_number < 90  # skip break slots
    ]
    return out


@router.post("/staff", status_code=201)
def add_staff(data: StaffIn, create_login: bool = Query(True), user: User = Depends(need("staff.manage")),
              db: Session = Depends(get_db)):
    """The staff ID is generated: <school><year>t<nnn>, or ...p<nnn> for the principal. Unless create_login=false, a
    login is created too (login = staff ID, one-time password, must be changed at first sign-in). It gets the
    standard teacher permissions (the principal also gets fees.view and announcements.manage), but never more than
    the person adding them holds."""
    _check_limit(db, user.school_id, Staff, "max_staff", "staff")
    fields = data.model_dump(exclude={"employee_id"})
    for _ in range(3):  # retry if two requests grab the same number
        s = Staff(school_id=user.school_id, employee_id=next_code(db, user.school_id, staff_letter(data.designation)),
                  **fields)
        db.add(s)
        db.flush()
        login = None
        if create_login:
            defaults = PRINCIPAL_DEFAULT if staff_letter(data.designation) == "p" else TEACHER_DEFAULT
            pw = gen_password()
            granted = sorted(set(defaults) & perm_set(user))
            db.add(User(school_id=user.school_id, username=s.employee_id, password_hash=hash_password(pw), role="staff",
                        full_name=s.name, permissions=",".join(granted), staff_id=s.id, must_change=True))
            login = {"username": s.employee_id, "temp_password": pw, "permissions": granted}
        try:
            db.commit()
            return {**_staff_out(s), "login": login}
        except IntegrityError:
            db.rollback()
    raise HTTPException(409, "Could not allocate a staff ID, please try again")


@router.put("/staff/{sid}")
def update_staff(sid: int, data: StaffIn, user: User = Depends(need("staff.manage")), db: Session = Depends(get_db)):
    s = get_owned(db, Staff, sid, user.school_id)
    for k, v in data.model_dump(exclude={"employee_id"}).items():  # the staff ID never changes
        setattr(s, k, v)
    db.commit()
    return _staff_out(s)


class ClassHeadIn(BaseModel):
    grade: str = Field(min_length=1, max_length=5)
    section: str = Field(pattern=r"^[A-Z]$")


@router.put("/staff/{sid}/class-head", status_code=204)
def set_class_head(sid: int, data: ClassHeadIn, user: User = Depends(school_user),
                   db: Session = Depends(get_db)):
    """Owner/admin assigns a staff member as the class head (section head) for a grade-section.
    Clears any existing class head for that section first so there is only ever one."""
    if user.role not in ("admin",) and "staff.manage" not in perm_set(user):
        raise HTTPException(403, "Only admin or staff managers can set a class head")
    s = get_owned(db, Staff, sid, user.school_id)
    key = f"{data.grade}{data.section}"
    # Clear any other staff currently marked as class head of this section
    for other in db.scalars(
        select(Staff).where(
            Staff.school_id == user.school_id,
            Staff.class_teacher_of == key,
            Staff.id != sid,
        )
    ):
        other.class_teacher_of = None
    s.class_teacher_of = key
    db.commit()


@router.delete("/staff/{sid}/class-head", status_code=204)
def remove_class_head(sid: int, user: User = Depends(school_user),
                      db: Session = Depends(get_db)):
    """Remove the class head designation from a staff member."""
    if user.role not in ("admin",) and "staff.manage" not in perm_set(user):
        raise HTTPException(403, "Only admin or staff managers can remove a class head")
    s = get_owned(db, Staff, sid, user.school_id)
    s.class_teacher_of = None
    db.commit()


@router.delete("/staff/{sid}", status_code=204)
def delete_staff(sid: int, user: User = Depends(need("staff.manage")), db: Session = Depends(get_db)):
    s = get_owned(db, Staff, sid, user.school_id)
    storage.remove(s.photo)
    for u in db.scalars(select(User).where(User.staff_id == s.id, User.school_id == user.school_id, User.role == "staff")):
        db.delete(u)  # a person who has left must not keep their sign-in
    db.delete(s)
    db.commit()


@router.get("/staff/{sid}/photo")
def staff_photo(sid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    return storage.serve(get_owned(db, Staff, sid, user.school_id).photo)


@router.post("/staff/{sid}/photo", status_code=204)
async def set_staff_photo(sid: int, request: Request, user: User = Depends(school_user),
                          db: Session = Depends(get_db)):
    s = get_owned(db, Staff, sid, user.school_id)
    if not ("staff.manage" in perm_set(user) or (user.role == "staff" and user.staff_id == s.id)):
        raise HTTPException(403, "Not allowed")
    data, ext = await storage.read_image(request)
    old = s.photo
    s.photo = storage.save(user.school_id, data, ext)
    db.commit()
    storage.remove(old)
