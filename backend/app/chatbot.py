"""School assistant. Answers are built only from database facts (no generated SQL), always scoped to
the asker's school and filtered by what their role/permissions allow.

If an LLM endpoint is configured, the (already permission-filtered) facts are sent to it purely to
phrase a friendlier reply; the grounded answer is the fallback.
"""
import logging
import re
from datetime import date

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import analytics
from .config import CURRENT_YEAR, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from .models import Chapter, Event, Goal, School, Staff, Student, Subject, User
from .security import perm_set

log = logging.getLogger("school.chatbot")
MAX_Q = 500
DENIED = "Sorry, you don't have access to that information."

SUGGESTIONS = [
    "How many students are in class 5?",
    "Which subjects does class 8 have?",
    "Who is the class teacher of class 3?",
    "What events are coming up?",
    "What are the chapters of Mathematics in class 5?",
    "What are our future goals?",
]
STAFF_SUGGESTIONS = SUGGESTIONS + ["Which students have pending fees?", "Who are the top performers?"]
STUDENT_SUGGESTIONS = ["How are my marks?", "What is my fee status?"] + SUGGESTIONS[:4]


def _money(v: float) -> str:
    return f"₹{v:,.0f}"


def _find_grade(q: str) -> str | None:
    if re.search(r"\bukg\b", q):
        return "UKG"
    if re.search(r"\blkg\b", q):
        return "LKG"
    m = re.search(r"(?:class|grade|std|standard)\s*(10|[1-9])\b", q) or re.search(r"\b(10|[1-9])(?:st|nd|rd|th)\b", q)
    return m.group(1) if m else None


def _find_students(db: Session, sid: int, q: str) -> list[Student]:
    students = db.scalars(select(Student).where(Student.school_id == sid)).all()
    full = [s for s in students if s.name.lower() in q]
    if full:
        return full[:5]
    words = set(re.findall(r"[a-z]{3,}", q))
    return [s for s in students if s.name.lower().split()[0] in words][:5]


def _find_staff(db: Session, sid: int, q: str) -> list[Staff]:
    staff = db.scalars(select(Staff).where(Staff.school_id == sid)).all()
    full = [s for s in staff if s.name.lower() in q]
    if full:
        return full[:5]
    words = set(re.findall(r"[a-z]{4,}", q))
    skip = {"mr", "mrs", "ms", "dr"}
    return [s for s in staff if any(
        p in words for p in s.name.lower().replace(".", "").split() if p not in skip and len(p) >= 4)][:5]


def _has(q: str, *words: str) -> bool:
    return any(w in q for w in words)


def _student_answer(db: Session, s: Student, q: str, can_fees: bool, own: bool) -> str:
    perf = analytics.performance(db, s, CURRENT_YEAR)
    head = f"{s.name} (Class {s.grade}-{s.section}, Adm. {s.admission_no})"
    fee_q = _has(q, "fee", "pending", "paid", "due", "balance", "payment")
    if fee_q:
        if not can_fees:
            return DENIED
        fee = analytics.fee_summary(db, s.id, CURRENT_YEAR)
        return (f"{head}: total fee {_money(fee['total'])}, paid {_money(fee['paid'])}, "
                f"pending {_money(fee['pending'])} ({fee['status']}).")
    if _has(q, "weak", "lack", "improv", "struggl", "poor", "behind"):
        if not perf["has_data"]:
            return f"{head} has no marks recorded for {CURRENT_YEAR} yet."
        return f"{head}: " + " ".join(perf["insights"])
    if _has(q, "parent", "guardian", "phone", "contact", "address", "email", "dob", "birth"):
        return (f"{head}: guardian {s.guardian_name}, phone {s.phone}, email {s.email or 'n/a'}, "
                f"DOB {s.dob.isoformat()}, address {s.address or 'n/a'}.")
    if not perf["has_data"]:
        return f"{head}: no marks recorded for {CURRENT_YEAR} yet."
    rank = analytics.class_rank(db, s, CURRENT_YEAR)
    rank_txt = f" Rank {rank['rank']} of {rank['out_of']} in the section." if rank else ""
    weak = ", ".join(perf["weak_subjects"]) or "none"
    best = perf["subjects"][-1]
    out = (f"{head}: overall {perf['overall_pct']}% (grade {perf['letter']}).{rank_txt} "
           f"Strongest: {best['subject']} ({best['avg_pct']}%). Needs attention: {weak}.")
    if can_fees:
        fee = analytics.fee_summary(db, s.id, CURRENT_YEAR)
        out += f" Fee pending {_money(fee['pending'])}."
    return out


def _staff_answer(s: Staff) -> str:
    ct = f", class teacher of {s.class_teacher_of}" if s.class_teacher_of else ""
    return (f"{s.name} ({s.employee_id}) is {s.designation}, {s.department}{ct}. "
            f"{s.qualification}, {s.experience_years} yrs experience. Teaches: {s.subjects or 'n/a'}. "
            f"Contact: {s.phone}, {s.email}.")


def answer_rules(db: Session, user: User, question: str) -> str:
    q = question.lower().strip()
    sid = user.school_id
    perms = perm_set(user)
    is_student = user.role == "student"
    can_students = "students.view" in perms
    can_fees = "fees.view" in perms or "fees.manage" in perms
    grade = _find_grade(q)

    # --- the logged-in student asking about themselves ---
    if is_student:
        me = db.get(Student, user.student_id)
        if me and re.search(r"\b(my|me|mine|myself|i)\b", q):
            return _student_answer(db, me, q, can_fees=True, own=True)
        mentioned = _find_students(db, sid, q)
        if any(s.id != user.student_id for s in mentioned):
            return DENIED
        if me and mentioned:
            return _student_answer(db, me, q, can_fees=True, own=True)
        if _has(q, "fee", "pending", "defaulter", "top", "topper", "rank", "at risk", "at-risk", "failing"):
            return DENIED

    # --- other students (needs permission) ---
    if not is_student:
        found = _find_students(db, sid, q)
        if found:
            if not can_students:
                return DENIED
            return "\n".join(_student_answer(db, s, q, can_fees, own=False) for s in found)

    staff = _find_staff(db, sid, q)
    if staff and not _has(q, "how many"):
        return "\n".join(_staff_answer(s) for s in staff)

    if _has(q, "class teacher") and grade:
        t = db.scalars(select(Staff).where(Staff.school_id == sid, Staff.class_teacher_of.like(f"{grade}-%"))).all()
        if t:
            return "; ".join(f"Class {x.class_teacher_of}: {x.name}" for x in t) + "."
        return f"No class teacher assigned for class {grade}."

    if _has(q, "chapter", "syllabus", "topics", "lesson"):
        subs = db.scalars(select(Subject).where(Subject.school_id == sid)).all()
        match = [s for s in subs if s.name.lower() in q and (not grade or s.grade == grade)]
        if not match:
            return "Tell me the subject and class, e.g. \"Chapters of Mathematics in class 5\"."
        parts = []
        for s in match[:3]:
            chs = db.scalars(select(Chapter).where(Chapter.subject_id == s.id).order_by(Chapter.number)).all()
            body = "; ".join(f"{c.number}. {c.title}" for c in chs) or "no chapters added yet"
            parts.append(f"{s.name} (Class {s.grade}): {body}.")
        return "\n".join(parts)

    if _has(q, "subject") and grade:
        names = db.scalars(select(Subject.name).where(Subject.school_id == sid, Subject.grade == grade)
                           .order_by(Subject.name)).all()
        if not names:
            return f"No subjects have been added for class {grade} yet."
        return f"Class {grade} subjects ({len(names)}): " + ", ".join(names) + "."

    if _has(q, "fee", "pending", "defaulter", "outstanding", "collection", "due"):
        if not can_fees:
            return DENIED
        d = analytics.dashboard(db, sid, CURRENT_YEAR)
        if grade:
            g = next(x for x in d["by_grade"] if x["grade"] == grade)
            return f"Class {grade}: {g['students']} students, pending fees {_money(g['pending_fee'])}."
        f = d["fees"]
        top = ", ".join(f"{x['name']} ({x['grade']}-{x['section']}, {_money(x['pending'])})" for x in d["top_defaulters"])
        return (f"Fees {CURRENT_YEAR}: total {_money(f['total'])}, collected {_money(f['paid'])} "
                f"({f['collection_pct']}%), pending {_money(f['pending'])}. Highest dues: {top or 'none'}.")

    if _has(q, "top", "topper", "best", "rank", "toppers", "performer"):
        if not can_students:
            return DENIED
        d = analytics.dashboard(db, sid, CURRENT_YEAR)
        return "Top performers: " + (", ".join(
            f"{x['name']} ({x['grade']}-{x['section']}, {x['pct']}%)" for x in d["top_students"]) or "no marks yet") + "."

    if _has(q, "at risk", "at-risk", "failing", "weak students", "low performing", "struggling"):
        if not can_students:
            return DENIED
        d = analytics.dashboard(db, sid, CURRENT_YEAR)
        if not d["at_risk"]:
            return "No students are currently below the 50% benchmark."
        return "Students needing support: " + ", ".join(
            f"{x['name']} ({x['grade']}-{x['section']}, {x['pct']}%)" for x in d["at_risk"]) + "."

    if _has(q, "how many", "count", "total", "number of") and _has(q, "teacher", "staff", "faculty"):
        n = db.scalar(select(func.count()).select_from(Staff).where(Staff.school_id == sid))
        return f"The school has {n} staff members."

    if _has(q, "how many", "count", "total", "number of", "strength") and _has(q, "student", "pupil", "children", "kids", "strength"):
        stmt = select(func.count()).select_from(Student).where(Student.school_id == sid)
        if grade:
            return f"Class {grade} has {db.scalar(stmt.where(Student.grade == grade))} students."
        return f"The school has {db.scalar(stmt)} students across LKG to 10th."

    if _has(q, "event", "upcoming", "function", "celebration", "sports day", "annual day"):
        ev = db.scalars(select(Event).where(Event.school_id == sid, Event.date >= date.today())
                        .order_by(Event.date).limit(5)).all()
        lead = "Upcoming events: "
        if not ev:
            ev = db.scalars(select(Event).where(Event.school_id == sid).order_by(Event.date.desc()).limit(5)).all()
            lead = "No upcoming events. Most recent: "
        if not ev:
            return "No events have been added yet."
        return lead + "; ".join(f"{e.title} on {e.date.isoformat()} at {e.location}" for e in ev) + "."

    if _has(q, "goal", "future", "vision", "plan", "roadmap"):
        gs = db.scalars(select(Goal).where(Goal.school_id == sid).order_by(Goal.target_year)).all()
        if not gs:
            return "No future goals have been added yet."
        return "Future goals: " + "; ".join(f"{g.title} ({g.target_year}, {g.progress}% done)" for g in gs) + "."

    if _has(q, "about", "school", "mission", "history", "founded", "address", "principal"):
        sc = db.get(School, sid)
        txt = " ".join(filter(None, [sc.name + ".", sc.about, sc.mission, sc.vision,
                                     f"Address: {sc.address}." if sc.address else None]))
        return txt or "About information is not set up yet."

    if _has(q, "subject"):
        return "Which class? For example: \"Which subjects does class 8 have?\""

    return ("I can answer about students, marks, fees, staff, subjects, chapters, events, goals and the school. "
            "Try: " + " | ".join(SUGGESTIONS[:3]))


def _llm_rephrase(question: str, facts: str) -> str | None:
    if not (LLM_BASE_URL and LLM_API_KEY and LLM_MODEL) or not LLM_BASE_URL.startswith("https://"):
        return None
    try:
        r = httpx.post(
            LLM_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={"model": LLM_MODEL, "temperature": 0.2, "messages": [
                {"role": "system", "content": "You are a school assistant. Answer ONLY using the FACTS. "
                 "If the facts do not contain the answer, say you don't have that information. Be concise."},
                {"role": "user", "content": f"FACTS:\n{facts}\n\nQUESTION: {question}"}]},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001 - fall back to the grounded answer
        log.warning("llm_unavailable")
        return None


def ask(db: Session, user: User, question: str) -> dict:
    question = question.strip()[:MAX_Q]
    grounded = answer_rules(db, user, question)
    phrased = _llm_rephrase(question, grounded) if grounded != DENIED else None
    sugg = STUDENT_SUGGESTIONS if user.role == "student" else (
        STAFF_SUGGESTIONS if perm_set(user) else SUGGESTIONS)
    return {"answer": phrased or grounded, "source": "llm" if phrased else "database", "suggestions": sugg}
