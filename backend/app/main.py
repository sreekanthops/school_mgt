import logging
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import analytics, chatbot
from .config import CORS_ORIGINS, CURRENT_YEAR
from .db import Base, engine, get_db
from .models import (EXAM_MAX, GRADES, Event, Fee, GalleryItem, Goal, Mark, Payment, Setting, Staff,
                     Student, Subject, User)
from .schemas import (ChatIn, FeeIn, LoginIn, MarkIn, PaymentIn, StaffIn, StaffOut, StudentIn,
                      StudentOut)
from .security import (admin_only, create_token, current_user, is_locked, record_failure,
                       verify_password)

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("school")

app = FastAPI(title="School Management API", version="1.0.0", docs_url="/docs")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
Base.metadata.create_all(engine)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.error("unhandled_error", exc_info=exc)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


def _get_student(db: Session, sid: int) -> Student:
    s = db.get(Student, sid)
    if not s:
        raise HTTPException(404, "Student not found")
    return s


# ---------- auth ----------
@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    if is_locked(data.username):
        raise HTTPException(429, "Too many failed attempts. Try again later.")
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not verify_password(data.password, user.password_hash):
        record_failure(data.username)
        raise HTTPException(401, "Invalid username or password")
    return {"token": create_token(user), "role": user.role, "name": user.full_name}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role, "name": user.full_name}


# ---------- meta / dashboard ----------
@app.get("/api/meta")
def meta(db: Session = Depends(get_db)):
    sections = sorted(set(db.scalars(select(Student.section))))
    return {"grades": GRADES, "sections": sections or ["A", "B"], "current_year": CURRENT_YEAR,
            "exams": [{"name": k, "max": v} for k, v in EXAM_MAX.items()]}


@app.get("/api/dashboard")
def dashboard(year: str = CURRENT_YEAR, db: Session = Depends(get_db), _: User = Depends(current_user)):
    d = analytics.dashboard(db, year)
    d["staff_count"] = db.scalar(select(func.count()).select_from(Staff))
    d["upcoming_events"] = [
        {"id": e.id, "title": e.title, "date": e.date.isoformat(), "category": e.category}
        for e in db.scalars(select(Event).where(Event.date >= date.today()).order_by(Event.date).limit(4))
    ]
    return d


# ---------- subjects ----------
@app.get("/api/subjects")
def subjects(grade: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(Subject).order_by(Subject.name)
    if grade:
        q = q.where(Subject.grade == grade)
    rows = db.scalars(q).all()
    grouped = {g: [] for g in GRADES}
    for s in rows:
        grouped[s.grade].append({"id": s.id, "name": s.name})
    teachers = db.scalars(select(Staff)).all()
    out = []
    for g in GRADES:
        if grade and g != grade:
            continue
        items = []
        for s in grouped[g]:
            t = [x.name for x in teachers if x.subjects and s["name"] in [p.strip() for p in x.subjects.split(",")]]
            items.append({**s, "teachers": t[:3]})
        out.append({"grade": g, "subjects": items})
    return out


# ---------- students ----------
@app.get("/api/students")
def list_students(
    q: Optional[str] = Query(None, max_length=100), grade: Optional[str] = None,
    section: Optional[str] = Query(None, max_length=2), page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100), year: str = CURRENT_YEAR,
    db: Session = Depends(get_db), _: User = Depends(current_user),
):
    stmt = select(Student)
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
    overall = analytics.student_overall_map(db, year)
    fees = analytics.fee_pending_map(db, year)
    items = [{
        "id": s.id, "admission_no": s.admission_no, "name": s.name, "gender": s.gender,
        "grade": s.grade, "section": s.section, "guardian_name": s.guardian_name, "phone": s.phone,
        "overall_pct": overall.get(s.id),
        "letter": analytics.grade_letter(overall[s.id]) if s.id in overall else None,
        "fee_pending": round(fees[s.id]["pending"], 2) if s.id in fees else 0,
    } for s in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/api/students", response_model=StudentOut, status_code=201)
def add_student(data: StudentIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = Student(**data.model_dump())
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Admission number already exists")
    return s


@app.put("/api/students/{sid}", response_model=StudentOut)
def update_student(sid: int, data: StudentIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = _get_student(db, sid)
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Admission number already exists")
    return s


@app.delete("/api/students/{sid}", status_code=204)
def delete_student(sid: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    db.delete(_get_student(db, sid))
    db.commit()


@app.get("/api/students/{sid}")
def student_detail(sid: int, year: str = CURRENT_YEAR, db: Session = Depends(get_db),
                   _: User = Depends(current_user)):
    s = _get_student(db, sid)
    years = analytics.student_years(db, sid)
    if CURRENT_YEAR not in years:
        years.append(CURRENT_YEAR)
    years = sorted(set(years), reverse=True)
    perf = analytics.performance(db, s, year)
    history = []
    for y in sorted(years):
        p = analytics.performance(db, s, y)
        if p["has_data"]:
            history.append({"year": y, "grade": p["grade"], "overall_pct": p["overall_pct"]})
    return {
        "student": StudentOut.model_validate(s).model_dump(mode="json"),
        "years": years, "selected_year": year, "performance": perf, "history": history,
        "rank": analytics.class_rank(db, s, year) if perf["has_data"] else None,
        "fees": analytics.fee_summary(db, sid, year),
    }


@app.get("/api/students/{sid}/marks")
def student_marks(sid: int, year: str = CURRENT_YEAR, db: Session = Depends(get_db),
                  _: User = Depends(current_user)):
    s = _get_student(db, sid)
    return analytics.performance(db, s, year)


@app.post("/api/students/{sid}/marks", status_code=201)
def upsert_mark(sid: int, data: MarkIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    _get_student(db, sid)
    subj = db.get(Subject, data.subject_id)
    if not subj:
        raise HTTPException(404, "Subject not found")
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
@app.get("/api/students/{sid}/fees")
def student_fees(sid: int, year: str = CURRENT_YEAR, db: Session = Depends(get_db),
                 _: User = Depends(current_user)):
    _get_student(db, sid)
    return analytics.fee_summary(db, sid, year)


@app.put("/api/students/{sid}/fees")
def set_fee(sid: int, data: FeeIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    _get_student(db, sid)
    f = db.scalar(select(Fee).where(Fee.student_id == sid, Fee.academic_year == data.academic_year))
    if f:
        f.total_amount = data.total_amount
    else:
        db.add(Fee(student_id=sid, academic_year=data.academic_year, total_amount=data.total_amount))
    db.commit()
    return analytics.fee_summary(db, sid, data.academic_year)


@app.post("/api/students/{sid}/payments", status_code=201)
def add_payment(sid: int, data: PaymentIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    _get_student(db, sid)
    summary = analytics.fee_summary(db, sid, data.academic_year)
    if summary["status"] == "No fee set":
        raise HTTPException(422, "No fee has been set for this year")
    if data.amount > summary["pending"]:
        raise HTTPException(422, f"Amount exceeds pending balance of {summary['pending']}")
    n = db.scalar(select(func.count()).select_from(Payment)) + 1
    db.add(Payment(student_id=sid, academic_year=data.academic_year, amount=data.amount,
                   paid_on=date.today(), mode=data.mode, receipt_no=f"RCPT-{date.today():%Y%m%d}-{n:05d}"))
    db.commit()
    return analytics.fee_summary(db, sid, data.academic_year)


# ---------- staff ----------
@app.get("/api/staff")
def list_staff(q: Optional[str] = Query(None, max_length=100), department: Optional[str] = None,
               db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(Staff).order_by(Staff.name)
    if q:
        stmt = stmt.where(or_(Staff.name.ilike(f"%{q}%"), Staff.subjects.ilike(f"%{q}%")))
    if department:
        stmt = stmt.where(Staff.department == department)
    rows = db.scalars(stmt).all()
    return [StaffOut.model_validate(r).model_dump(mode="json") for r in rows]


@app.post("/api/staff", response_model=StaffOut, status_code=201)
def add_staff(data: StaffIn, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = Staff(**data.model_dump())
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Employee ID already exists")
    return s


@app.delete("/api/staff/{sid}", status_code=204)
def delete_staff(sid: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    s = db.get(Staff, sid)
    if not s:
        raise HTTPException(404, "Staff not found")
    db.delete(s)
    db.commit()


# ---------- public content ----------
@app.get("/api/events")
def events(db: Session = Depends(get_db)):
    return [{"id": e.id, "title": e.title, "description": e.description, "date": e.date.isoformat(),
             "location": e.location, "category": e.category}
            for e in db.scalars(select(Event).order_by(Event.date.desc()))]


@app.get("/api/gallery")
def gallery(db: Session = Depends(get_db)):
    return [{"id": g.id, "title": g.title, "category": g.category, "caption": g.caption,
             "image_url": g.image_url, "taken_on": g.taken_on.isoformat()}
            for g in db.scalars(select(GalleryItem).order_by(GalleryItem.taken_on.desc()))]


@app.get("/api/goals")
def goals(db: Session = Depends(get_db)):
    return [{"id": g.id, "title": g.title, "description": g.description, "target_year": g.target_year,
             "progress": g.progress, "status": g.status}
            for g in db.scalars(select(Goal).order_by(Goal.target_year))]


@app.get("/api/about")
def about(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.scalars(select(Setting))}


# ---------- chatbot ----------
@app.post("/api/chat")
def chat(data: ChatIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return chatbot.ask(db, data.question)


@app.get("/api/health")
def health():
    return {"status": "ok"}
