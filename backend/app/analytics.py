"""Performance, fee and dashboard analytics. Pure functions over the DB."""
from collections import defaultdict
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import EXAM_MAX, EXAMS, GRADES, Fee, Mark, Payment, Student, Subject

WEAK_BELOW = 50.0  # percent
EXAM_ORDER = [e for e, _ in EXAMS]


def pct(score: float, mx: float) -> float:
    return round(score * 100 / mx, 1) if mx else 0.0


def grade_letter(p: float) -> str:
    for cut, letter in ((90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C"), (40, "D")):
        if p >= cut:
            return letter
    return "E"


def student_years(db: Session, student_id: int) -> list[str]:
    rows = db.scalars(select(Mark.academic_year).where(Mark.student_id == student_id).distinct())
    return sorted(rows)


def performance(db: Session, student: Student, year: str) -> dict:
    rows = db.execute(
        select(Mark, Subject)
        .join(Subject, Subject.id == Mark.subject_id)
        .where(Mark.student_id == student.id, Mark.academic_year == year)
    ).all()
    if not rows:
        return {"year": year, "grade": None, "has_data": False, "subjects": [], "exams": [],
                "overall_pct": None, "letter": None, "weak_subjects": [], "strong_subjects": [],
                "insights": [], "marks": []}

    grade = rows[0][1].grade
    by_subject = defaultdict(dict)
    by_exam = defaultdict(list)
    marks = []
    for m, s in rows:
        p = pct(m.score, m.max_score)
        by_subject[s.name][m.exam] = p
        by_exam[m.exam].append(p)
        marks.append({"subject": s.name, "exam": m.exam, "score": m.score, "max": m.max_score, "pct": p})

    subjects = []
    for name, exams in by_subject.items():
        avg = round(mean(exams.values()), 1)
        ordered = [exams[e] for e in EXAM_ORDER if e in exams]
        trend = round(ordered[-1] - ordered[0], 1) if len(ordered) > 1 else 0.0
        subjects.append({"subject": name, "avg_pct": avg, "exams": exams, "trend": trend})
    subjects.sort(key=lambda x: x["avg_pct"])

    exams = [{"exam": e, "avg_pct": round(mean(by_exam[e]), 1), "max": EXAM_MAX[e]}
             for e in EXAM_ORDER if e in by_exam]
    overall = round(mean(s["avg_pct"] for s in subjects), 1)

    weak = [s for s in subjects if s["avg_pct"] < WEAK_BELOW or s["trend"] <= -10]
    strong = [s for s in subjects if s["avg_pct"] >= 85][::-1]

    insights = []
    for s in weak:
        if s["avg_pct"] < WEAK_BELOW:
            insights.append(f"{s['subject']}: average {s['avg_pct']}% is below the {WEAK_BELOW:.0f}% pass benchmark. Needs focused practice.")
        else:
            insights.append(f"{s['subject']}: dropped {abs(s['trend'])} points from first to latest test. Review recent topics.")
    if len(exams) > 1 and exams[-1]["avg_pct"] > exams[0]["avg_pct"] + 5:
        insights.append("Overall performance is improving across tests.")
    if not insights:
        insights.append("No weak areas detected. Keep it up.")

    return {
        "year": year, "grade": grade, "has_data": True, "subjects": subjects, "exams": exams,
        "overall_pct": overall, "letter": grade_letter(overall),
        "weak_subjects": [s["subject"] for s in weak], "strong_subjects": [s["subject"] for s in strong],
        "insights": insights, "marks": marks,
    }


def fee_summary(db: Session, student_id: int, year: str) -> dict:
    fee = db.scalar(select(Fee).where(Fee.student_id == student_id, Fee.academic_year == year))
    total = fee.total_amount if fee else 0.0
    pays = db.scalars(
        select(Payment).where(Payment.student_id == student_id, Payment.academic_year == year)
        .order_by(Payment.paid_on)
    ).all()
    paid = round(sum(p.amount for p in pays), 2)
    return {
        "year": year, "total": total, "paid": paid, "pending": round(max(total - paid, 0), 2),
        "status": "No fee set" if not fee else ("Paid" if paid >= total else ("Partial" if paid else "Unpaid")),
        "payments": [{"id": p.id, "amount": p.amount, "paid_on": p.paid_on.isoformat(),
                      "mode": p.mode, "receipt_no": p.receipt_no} for p in pays],
    }


def student_overall_map(db: Session, school_id: int, year: str) -> dict[int, float]:
    """student_id -> overall % for a year (one school), in one query."""
    rows = db.execute(
        select(Mark.student_id, func.sum(Mark.score * 100.0 / Mark.max_score), func.count())
        .join(Student, Student.id == Mark.student_id)
        .where(Mark.academic_year == year, Student.school_id == school_id)
        .group_by(Mark.student_id)
    ).all()
    return {sid: round(total / n, 1) for sid, total, n in rows}


def fee_pending_map(db: Session, school_id: int, year: str) -> dict[int, dict]:
    fees = {f.student_id: f.total_amount for f in db.scalars(
        select(Fee).join(Student, Student.id == Fee.student_id)
        .where(Fee.academic_year == year, Student.school_id == school_id))}
    paid = dict(db.execute(
        select(Payment.student_id, func.sum(Payment.amount))
        .join(Student, Student.id == Payment.student_id)
        .where(Payment.academic_year == year, Student.school_id == school_id)
        .group_by(Payment.student_id)).all())
    return {sid: {"total": t, "paid": paid.get(sid, 0.0), "pending": max(t - paid.get(sid, 0.0), 0.0)}
            for sid, t in fees.items()}


def class_rank(db: Session, student: Student, year: str) -> dict | None:
    overall = student_overall_map(db, student.school_id, year)
    peers = db.scalars(select(Student.id).where(
        Student.school_id == student.school_id, Student.grade == student.grade,
        Student.section == student.section)).all()
    ranked = sorted(((overall[i], i) for i in peers if i in overall), reverse=True)
    for pos, (_, sid) in enumerate(ranked, 1):
        if sid == student.id:
            return {"rank": pos, "out_of": len(ranked)}
    return None


def dashboard(db: Session, school_id: int, year: str) -> dict:
    students = db.scalars(select(Student).where(Student.school_id == school_id)).all()
    overall = student_overall_map(db, school_id, year)
    fees = fee_pending_map(db, school_id, year)

    by_grade = []
    for g in GRADES:
        ids = [s.id for s in students if s.grade == g]
        scores = [overall[i] for i in ids if i in overall]
        by_grade.append({
            "grade": g, "students": len(ids),
            "avg_pct": round(mean(scores), 1) if scores else None,
            "pending_fee": round(sum(fees[i]["pending"] for i in ids if i in fees), 2),
        })

    total = sum(f["total"] for f in fees.values())
    paid = sum(f["paid"] for f in fees.values())
    dist = {"90+": 0, "75-89": 0, "60-74": 0, "50-59": 0, "<50": 0}
    for v in overall.values():
        dist["90+" if v >= 90 else "75-89" if v >= 75 else "60-74" if v >= 60 else "50-59" if v >= 50 else "<50"] += 1

    by_id = {s.id: s for s in students}
    top = sorted(overall.items(), key=lambda kv: kv[1], reverse=True)[:5]
    at_risk = sorted(((i, v) for i, v in overall.items() if v < WEAK_BELOW), key=lambda kv: kv[1])[:5]
    defaulters = sorted(((i, f["pending"]) for i, f in fees.items() if f["pending"] > 0),
                        key=lambda kv: kv[1], reverse=True)[:5]
    brief = lambda i, v, key: {"id": i, "name": by_id[i].name, "grade": by_id[i].grade,
                               "section": by_id[i].section, key: v}
    return {
        "year": year, "total_students": len(students),
        "avg_pct": round(mean(overall.values()), 1) if overall else None,
        "fees": {"total": round(total, 2), "paid": round(paid, 2), "pending": round(total - paid, 2),
                 "collection_pct": round(paid * 100 / total, 1) if total else 0},
        "by_grade": by_grade, "distribution": dist,
        "top_students": [brief(i, v, "pct") for i, v in top],
        "at_risk": [brief(i, v, "pct") for i, v in at_risk],
        "top_defaulters": [brief(i, v, "pending") for i, v in defaulters],
    }
