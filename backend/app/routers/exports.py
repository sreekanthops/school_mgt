"""CSV / PDF exports: student lists, marks, fee register, report cards and fee receipts."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analytics
from ..db import get_db
from ..deps import can_see_fees, can_see_student, get_student, year_of
from ..models import GRADES, Mark, Payment, School, Student, Subject, User
from ..reports import (BODY, H1, H2, HEADC, SUB, Paragraph, Spacer, build, csv_response, escape, grid, kv_table, mm, P,
                       pdf_response, rs, table_pdf)
from ..schemas import YEAR
from ..security import need, school_user

router = APIRouter(prefix="/api")
FMT = Query("csv", pattern="^(csv|pdf)$")


def _school_name(db: Session, user: User) -> str:
    return db.get(School, user.school_id).name


def _students(db: Session, user: User, grade: Optional[str], section: Optional[str]) -> list[Student]:
    if grade and grade not in GRADES:
        raise HTTPException(422, "Unknown class")
    stmt = select(Student).where(Student.school_id == user.school_id)
    if grade:
        stmt = stmt.where(Student.grade == grade)
    if section:
        stmt = stmt.where(Student.section == section.upper()[:1])
    return list(db.scalars(stmt.order_by(Student.grade, Student.section, Student.name)))


def _cls(s: Student) -> str:
    return f"{s.grade}-{s.section}"


@router.get("/export/students")
def export_students(format: str = FMT, grade: Optional[str] = None, section: Optional[str] = Query(None, max_length=2),
                    user: User = Depends(need("students.view")), db: Session = Depends(get_db)):
    rows = [[s.admission_no, s.name, _cls(s), s.gender, s.dob.isoformat(), s.guardian_name, s.phone, s.email,
             s.blood_group, s.address] for s in _students(db, user, grade, section)]
    head = ["Student ID", "Name", "Class", "Gender", "Date of birth", "Guardian", "Phone", "Email", "Blood group", "Address"]
    if format == "csv":
        return csv_response(head, rows, "students")
    pdf_rows = [r[:7] for r in rows]
    return pdf_response(table_pdf(_school_name(db, user), "Student list", f"{len(rows)} students", head[:7], pdf_rows), "students")


@router.get("/export/marks")
def export_marks(format: str = FMT, year: Optional[str] = Query(None, pattern=YEAR), grade: Optional[str] = None,
                 section: Optional[str] = Query(None, max_length=2),
                 user: User = Depends(need("students.view")), db: Session = Depends(get_db)):
    year = year_of(db, user.school_id, year)
    studs = _students(db, user, grade, section)
    by_id = {s.id: s for s in studs}
    marks = db.execute(select(Mark, Subject).join(Subject, Subject.id == Mark.subject_id)
                       .where(Mark.academic_year == year, Mark.student_id.in_(list(by_id) or [0]))).all()
    if format == "csv":
        order = {s.id: i for i, s in enumerate(studs)}
        ex = {e: i for i, e in enumerate(analytics.EXAM_ORDER)}
        rows = sorted(marks, key=lambda r: (order[r[0].student_id], r[1].name, ex.get(r[0].exam, 9)))
        return csv_response(
            ["Student ID", "Name", "Class", "Subject", "Test", "Score", "Out of", "Percent"],
            [[by_id[m.student_id].admission_no, by_id[m.student_id].name, _cls(by_id[m.student_id]), sub.name, m.exam,
              m.score, m.max_score, analytics.pct(m.score, m.max_score)] for m, sub in rows], f"marks-{year}")
    per: dict[int, dict[str, list[float]]] = {}
    for m, _sub in marks:
        per.setdefault(m.student_id, {}).setdefault(m.exam, []).append(analytics.pct(m.score, m.max_score))
    head = ["Student ID", "Name", "Class", *analytics.EXAM_ORDER, "Overall %", "Grade"]
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    rows = []
    for s in studs:
        e = per.get(s.id, {})
        ov = avg([v for xs in e.values() for v in xs])
        rows.append([s.admission_no, s.name, _cls(s),
                     *[("" if x not in e else f"{avg(e[x])}%") for x in analytics.EXAM_ORDER],
                     "" if ov is None else f"{ov}%", analytics.grade_letter(ov) if ov is not None else ""])
    return pdf_response(table_pdf(_school_name(db, user), f"Marks summary {year}", "average % per test", head, rows), f"marks-{year}")


@router.get("/export/fees")
def export_fees(format: str = FMT, year: Optional[str] = Query(None, pattern=YEAR), grade: Optional[str] = None,
                status: Optional[str] = Query(None, max_length=20),
                user: User = Depends(need("fees.view", "fees.manage")), db: Session = Depends(get_db)):
    year = year_of(db, user.school_id, year)
    fm = analytics.fee_pending_map(db, user.school_id, year)
    rows = []
    for s in _students(db, user, grade, None):
        f = fm.get(s.id)
        total, paid = (f["total"], f["paid"]) if f else (0.0, 0.0)
        pending = max(total - paid, 0.0)
        st = "No fee set" if not f else "Paid" if pending <= 0 else "Partial" if paid > 0 else "Unpaid"
        if status and st != status:
            continue
        rows.append([s.admission_no, s.name, _cls(s), total, paid, pending, st])
    head = ["Student ID", "Name", "Class", "Total", "Paid", "Pending", "Status"]
    if format == "csv":
        return csv_response(head, rows, f"fees-{year}")
    t, p = sum(r[3] for r in rows), sum(r[4] for r in rows)
    pdf_rows = [[*r[:3], rs(r[3]), rs(r[4]), rs(r[5]), r[6]] for r in rows]
    pdf_rows.append(["", "TOTAL", "", rs(t), rs(p), rs(max(t - p, 0)), ""])
    return pdf_response(table_pdf(_school_name(db, user), f"Fee register {year}", f"{len(rows)} students",
                                  head, pdf_rows, align_right=(3, 4, 5)), f"fees-{year}")


@router.get("/students/{sid}/report-card")
def report_card(sid: int, year: Optional[str] = Query(None, pattern=YEAR), user: User = Depends(school_user),
                db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    if not can_see_student(user, sid):
        raise HTTPException(403, "You can only view your own details")
    year = year_of(db, user.school_id, year)
    perf = analytics.performance(db, s, year)
    school = _school_name(db, user)
    story = [Paragraph(escape(school), H1), Paragraph("Progress report - " + escape(year), SUB),
             kv_table([("Student", s.name), ("Student ID", s.admission_no), ("Class", f"{s.grade}-{s.section}"),
                       ("Guardian", s.guardian_name)])]
    if not perf["has_data"]:
        story += [Spacer(1, 6 * mm), Paragraph("No marks have been recorded for this year.", BODY)]
    else:
        exams = analytics.EXAM_ORDER
        head = ["Subject", *exams, "Average"]
        rows = [[P(x["subject"]), *[P(f"{x['exams'][e]}%" if e in x["exams"] else "-") for e in exams], P(f"{x['avg_pct']}%")]
                for x in sorted(perf["subjects"], key=lambda r: r["subject"])]
        story += [Paragraph("Marks (percent of each test)", H2), grid([[P(h, HEADC) for h in head]] + rows, align_right=range(1, len(head)))]
        rank = analytics.class_rank(db, s, year)
        story += [Paragraph("Result", H2), kv_table([
            ("Overall", f"{perf['overall_pct']}%  -  grade {perf['letter']}"),
            ("Section rank", f"{rank['rank']} of {rank['out_of']}" if rank else "-"),
            ("Needs attention", ", ".join(perf["weak_subjects"]) or "None"),
            ("Strongest", ", ".join(perf["strong_subjects"]) or "-")])]
    return pdf_response(build(story, school), f"report-card-{s.admission_no}-{year}")


@router.get("/students/{sid}/payments/{pid}/receipt")
def fee_receipt(sid: int, pid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    s = get_student(db, user, sid)
    if not can_see_fees(user, sid):
        raise HTTPException(403, "You do not have access to fee details")
    p = db.get(Payment, pid)
    if not p or p.student_id != sid:
        raise HTTPException(404, "Not found")
    fee = analytics.fee_summary(db, sid, p.academic_year)
    school = _school_name(db, user)
    story = [Paragraph(escape(school), H1), Paragraph("Fee receipt", SUB),
             kv_table([("Receipt no.", p.receipt_no), ("Date", p.paid_on.strftime("%d %b %Y")),
                       ("Student", f"{s.name} ({s.admission_no})"), ("Class", f"{s.grade}-{s.section}"),
                       ("Academic year", p.academic_year), ("Payment mode", p.mode), ("Amount received", rs(p.amount))]),
             Paragraph("Fee position for the year", H2),
             kv_table([("Total fee", rs(fee["total"])), ("Paid so far", rs(fee["paid"])), ("Pending", rs(fee["pending"]))]),
             Spacer(1, 8 * mm), Paragraph("This is a computer generated receipt.", SUB)]
    return pdf_response(build(story, school), f"receipt-{p.receipt_no}")
