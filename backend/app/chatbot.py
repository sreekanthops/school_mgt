"""School assistant. Answers are built only from database facts (no generated SQL), always scoped to
the asker's school and filtered by what their role/permissions allow.

If an LLM endpoint is configured, the (already permission-filtered) facts are sent to it purely to
phrase a friendlier reply; the grounded answer is the fallback.
"""
import logging
import re
from datetime import date, timedelta

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import analytics
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from .deps import year_of
from .models import Announcement, Attendance, AssistantMessage, Chapter, Event, Goal, School, Staff, Student, Subject, User
from .routers import announcements, attendance
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
STAFF_SUGGESTIONS = SUGGESTIONS + ["Which students have pending fees?", "Who are the top performers?",
                                   "Who has low attendance?", "Any new announcements?"]
STUDENT_SUGGESTIONS = ["How are my marks?", "What is my fee status?", "What is my attendance?"] + SUGGESTIONS[:4]


def _money(v: float) -> str:
    return f"₹{v:,.0f}"


def _tone(p: float | None) -> str:
    return "" if p is None else "good" if p >= 75 else "warn" if p >= 50 else "bad"


def R(text: str, stats=None, bars=None, actions=None) -> dict:
    """A reply: plain text plus optional stat cards, percentage bars and navigation buttons."""
    return {"text": text, "stats": stats or [], "bars": bars or [], "actions": actions or []}


def stat(label: str, value, tone: str = "") -> dict:
    return {"label": label, "value": str(value), "tone": tone}


def bar(label: str, pct: float, sub: str = "") -> dict:
    return {"label": label, "pct": round(pct, 1), "tone": _tone(pct), "sub": sub}


def act(label: str, to: str) -> dict:
    return {"label": label, "to": to}


def _user_of(db: Session, *, student_id: int | None = None, staff_id: int | None = None) -> int | None:
    col, val = (User.student_id, student_id) if student_id else (User.staff_id, staff_id)
    return db.scalar(select(User.id).where(col == val, User.active.is_(True)).limit(1))


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


def _msg_action(db: Session, viewer: User, *, student: Student | None = None, staff: Staff | None = None):
    """A "Message" button, only when that person has a login the viewer is allowed to write to."""
    if student is not None:
        if viewer.role == "student":  # students may only write to staff
            return None
        uid, name = _user_of(db, student_id=student.id), student.name
    else:
        uid, name = _user_of(db, staff_id=staff.id), staff.name
    if not uid or uid == viewer.id:
        return None
    return act(f"Message {name.split()[0]}", f"/messages?to={uid}")


def _student_answer(db: Session, viewer: User, s: Student, q: str, can_fees: bool, base: str, multi: bool = False) -> dict:
    """`base` is the route prefix for the profile: /students/<id> or /me."""
    CURRENT_YEAR = year_of(db, s.school_id)
    perf = analytics.performance(db, s, CURRENT_YEAR)
    head = f"{s.name} · Class {s.grade}-{s.section} · ID {s.admission_no}"
    open_btn = act("Open profile", base)
    fee_q = _has(q, "fee", "pending", "paid", "due", "balance", "payment")
    if fee_q:
        if not can_fees:
            return R(DENIED)
        fee = analytics.fee_summary(db, s.id, CURRENT_YEAR)
        paid_pct = (fee["paid"] * 100 / fee["total"]) if fee["total"] else 0
        return R(f"{head}\nFee status: {fee['status']}.",
                 stats=[stat("Total", _money(fee["total"])), stat("Paid", _money(fee["paid"]), "good"),
                        stat("Pending", _money(fee["pending"]), "bad" if fee["pending"] else "good")],
                 bars=[bar("Fee paid", paid_pct)], actions=[act("Fee details", f"{base}?tab=fees"), open_btn])
    if _has(q, "attendance", "absent", "absence", "present", "bunk"):
        a = _attendance_of(db, s)
        if a["month"]["days"] == 0:
            return R(f"{head}\nNo attendance has been recorded yet.", actions=[open_btn])
        m = a["month"]
        return R(f"{head}\nAttendance over the last {attendance.WINDOW_DAYS} days: {m['pct']}% "
                 f"({m['absent']} absent of {m['days']} school days)."
                 + (f" Below the {attendance.LOW_PCT:.0f}% requirement." if a["low"] else ""),
                 stats=[stat("Attendance", f"{m['pct']}%", "bad" if a["low"] else "good"), stat("Absent", m["absent"]),
                        stat("Late", m["late"])],
                 bars=[bar("Attendance", m["pct"])], actions=[act("Open profile", f"{base}?tab=attendance"), open_btn])
    if _has(q, "weak", "lack", "improv", "struggl", "poor", "behind"):
        if not perf["has_data"]:
            return R(f"{head}\nNo marks recorded for {CURRENT_YEAR} yet.", actions=[open_btn])
        weakest = perf["subjects"][:4]
        return R(f"{head}\n" + "\n".join("• " + i for i in perf["insights"]),
                 stats=[stat("Overall", f"{perf['overall_pct']}%", _tone(perf["overall_pct"])),
                        stat("Weak areas", len(perf["weak_subjects"]), "bad" if perf["weak_subjects"] else "good")],
                 bars=[bar(x["subject"], x["avg_pct"]) for x in weakest],
                 actions=[act("Marks & performance", f"{base}?tab=marks"), open_btn])
    if _has(q, "parent", "guardian", "phone", "contact", "address", "email", "dob", "birth"):
        return R(f"{head}\nGuardian: {s.guardian_name}\nPhone: {s.phone}\nEmail: {s.email or 'n/a'}\n"
                 f"DOB: {s.dob.isoformat()}\nAddress: {s.address or 'n/a'}", actions=[open_btn])
    if not perf["has_data"]:
        return R(f"{head}\nNo marks recorded for {CURRENT_YEAR} yet.", actions=[open_btn])
    rank = analytics.class_rank(db, s, CURRENT_YEAR)
    best = perf["subjects"][-1]
    weak = ", ".join(perf["weak_subjects"]) or "none"
    stats = [stat("Overall", f"{perf['overall_pct']}%", _tone(perf["overall_pct"])), stat("Grade", perf["letter"])]
    if rank:
        stats.append(stat("Section rank", f"{rank['rank']} / {rank['out_of']}"))
    if can_fees:
        fee = analytics.fee_summary(db, s.id, CURRENT_YEAR)
        stats.append(stat("Fee pending", _money(fee["pending"]), "bad" if fee["pending"] else "good"))
    acts = [act("Marks & performance", f"{base}?tab=marks"), open_btn]
    if can_fees:
        acts.insert(1, act("Fees", f"{base}?tab=fees"))
    m = _msg_action(db, viewer, student=s) if base != "/me" else None
    if m:
        acts.append(m)
    return R(f"{head}\nStrongest: {best['subject']} ({best['avg_pct']}%). Needs attention: {weak}.",
             stats=stats, bars=[bar(x["subject"], x["avg_pct"]) for x in perf["subjects"][:8]], actions=acts)


def _attendance_of(db: Session, s: Student) -> dict:
    rows = [(a.day, a.status) for a in db.scalars(select(Attendance).where(
        Attendance.student_id == s.id, Attendance.day >= date.today() - timedelta(days=attendance.WINDOW_DAYS)))]
    m = attendance._summary(rows)
    return {"month": m, "low": m["days"] >= attendance.MIN_DAYS and m["pct"] < attendance.LOW_PCT}


def _staff_answer(db: Session, viewer: User, s: Staff) -> dict:
    ct = f"Class teacher of {s.class_teacher_of}\n" if s.class_teacher_of else ""
    acts = [act("Open profile", f"/staff/{s.id}")]
    m = _msg_action(db, viewer, staff=s)
    if m:
        acts.append(m)
    return R(f"{s.name} · {s.designation}, {s.department}\n{ct}{s.qualification} · {s.experience_years} yrs experience\n"
             f"Teaches: {s.subjects or 'n/a'}\nContact: {s.phone} · {s.email}",
             stats=[stat("Experience", f"{s.experience_years} yrs"), stat("ID", s.employee_id)], actions=acts)


def _who_buttons(rows, tone_key: str = "pct") -> list[dict]:
    return [act(f"{x['name']} · {x['grade']}-{x['section']}", f"/students/{x['id']}") for x in rows]


def answer_rules(db: Session, user: User, question: str) -> dict:
    q = question.lower().strip()
    sid = user.school_id
    CURRENT_YEAR = year_of(db, sid)
    perms = perm_set(user)
    is_student = user.role == "student"
    can_students = "students.view" in perms
    can_fees = "fees.view" in perms or "fees.manage" in perms
    grade = _find_grade(q)

    # --- the logged-in student asking about themselves ---
    if is_student:
        me = db.get(Student, user.student_id)
        if me and re.search(r"\b(my|me|mine|myself|i)\b", q):
            return _student_answer(db, user, me, q, can_fees=True, base="/me")
        mentioned = _find_students(db, sid, q)
        if any(s.id != user.student_id for s in mentioned):
            return R(DENIED)
        if me and mentioned:
            return _student_answer(db, user, me, q, can_fees=True, base="/me")
        if _has(q, "fee", "pending", "defaulter", "top", "topper", "rank", "at risk", "at-risk", "failing"):
            return R(DENIED)

    # --- other students (needs permission) ---
    if not is_student:
        found = _find_students(db, sid, q)
        if found:
            if not can_students:
                return R(DENIED)
            if len(found) == 1:
                return _student_answer(db, user, found[0], q, can_fees, base=f"/students/{found[0].id}")
            lines = []
            for s in found:
                p = analytics.performance(db, s, CURRENT_YEAR)
                lines.append(f"• {s.name} (Class {s.grade}-{s.section}): "
                             + (f"{p['overall_pct']}% · grade {p['letter']}" if p["has_data"] else "no marks yet"))
            return R(f"I found {len(found)} students:\n" + "\n".join(lines),
                     actions=[act(f"{s.name} · {s.grade}-{s.section}", f"/students/{s.id}") for s in found])

    staff = _find_staff(db, sid, q)
    if staff and not _has(q, "how many"):
        if len(staff) == 1:
            return _staff_answer(db, user, staff[0])
        return R(f"I found {len(staff)} staff members:\n" + "\n".join(
            f"• {x.name} — {x.designation}" for x in staff), actions=[act(x.name, f"/staff/{x.id}") for x in staff])

    if _has(q, "class teacher") and grade:
        t = db.scalars(select(Staff).where(Staff.school_id == sid, Staff.class_teacher_of.like(f"{grade}-%"))).all()
        if t:
            return R("\n".join(f"Class {x.class_teacher_of}: {x.name}" for x in t),
                     actions=[act(x.name, f"/staff/{x.id}") for x in t])
        return R(f"No class teacher assigned for class {grade}.", actions=[act("Open staff", "/staff")])

    if _has(q, "chapter", "syllabus", "topics", "lesson"):
        subs = db.scalars(select(Subject).where(Subject.school_id == sid)).all()
        match = [s for s in subs if s.name.lower() in q and (not grade or s.grade == grade)]
        if not match:
            return R("Tell me the subject and class, e.g. \"Chapters of Mathematics in class 5\".")
        parts = []
        for s in match[:3]:
            chs = db.scalars(select(Chapter).where(Chapter.subject_id == s.id).order_by(Chapter.number)).all()
            body = "\n".join(f"  {c.number}. {c.title}" for c in chs) or "  no chapters added yet"
            parts.append(f"{s.name} · Class {s.grade} ({len(chs)} chapters)\n{body}")
        return R("\n\n".join(parts), actions=[act(f"Open {s.name} (Class {s.grade})", f"/subjects/{s.id}") for s in match[:3]])

    if _has(q, "subject") and grade:
        rows = db.execute(select(Subject.id, Subject.name).where(Subject.school_id == sid, Subject.grade == grade)
                          .order_by(Subject.name)).all()
        if not rows:
            return R(f"No subjects have been added for class {grade} yet.", actions=[act("Open subjects", "/subjects")])
        return R(f"Class {grade} has {len(rows)} subjects:\n" + "\n".join(f"• {n}" for _, n in rows),
                 stats=[stat("Subjects", len(rows))],
                 actions=[act(n, f"/subjects/{i}") for i, n in rows[:8]] + [act("All subjects", f"/subjects?grade={grade}")])

    if _has(q, "announcement", "notice", "circular"):
        rows = db.scalars(announcements._visible(db, user).order_by(Announcement.pinned.desc(), Announcement.id.desc()).limit(4)).all()
        if not rows:
            return R("There are no announcements right now.", actions=[act("Open announcements", "/announcements")])
        return R("Latest announcements:\n" + "\n".join(f"• {a.title} ({a.created_at:%d %b})" for a in rows),
                 actions=[act("Open announcements", "/announcements")])

    if _has(q, "attendance", "absent", "absentee", "bunk"):
        if is_student or not ({"attendance.manage", "students.view"} & perms):
            return R(DENIED)
        al = attendance.low_attendance(db, sid)
        if not al:
            return R(f"No student is below {attendance.LOW_PCT:.0f}% attendance in the last {attendance.WINDOW_DAYS} days.",
                     actions=[act("Attendance", "/attendance")])
        return R(f"{len(al)} student{'s' if len(al) != 1 else ''} need attention (below {attendance.LOW_PCT:.0f}% in the last "
                 f"{attendance.WINDOW_DAYS} days, or absent {attendance.STREAK}+ days in a row):\n"
                 + "\n".join(f"• {x['name']} ({x['grade']}-{x['section']}): {x['pct']}%" for x in al[:6]),
                 stats=[stat("Flagged", len(al), "bad")], actions=[act(f"{x['name']} · {x['grade']}-{x['section']}", f"/students/{x['id']}") for x in al[:5]]
                 + [act("Attendance report", "/attendance")])

    if _has(q, "fee", "pending", "defaulter", "outstanding", "collection", "due"):
        if not can_fees:
            return R(DENIED)
        d = analytics.dashboard(db, sid, CURRENT_YEAR)
        if grade:
            g = next(x for x in d["by_grade"] if x["grade"] == grade)
            return R(f"Class {grade}: {g['students']} students.",
                     stats=[stat("Students", g["students"]), stat("Pending fees", _money(g["pending_fee"]), "bad" if g["pending_fee"] else "good")],
                     actions=[act("Fee register", "/fees")])
        f = d["fees"]
        top = d["top_defaulters"]
        return R(f"Fees for {CURRENT_YEAR}." + (" Highest dues:" if top else " No pending dues."),
                 stats=[stat("Total", _money(f["total"])), stat("Collected", _money(f["paid"]), "good"),
                        stat("Pending", _money(f["pending"]), "bad" if f["pending"] else "good"),
                        stat("Collection", f"{f['collection_pct']}%", _tone(f["collection_pct"]))],
                 bars=[bar("Collection", f["collection_pct"])],
                 actions=[act(f"{x['name']} · {_money(x['pending'])}", f"/students/{x['id']}?tab=fees") for x in top] + [act("Fee register", "/fees")])

    if _has(q, "top", "topper", "best", "rank", "toppers", "performer"):
        if not can_students:
            return R(DENIED)
        d = analytics.dashboard(db, sid, CURRENT_YEAR)
        if not d["top_students"]:
            return R("No marks have been recorded yet.")
        return R("Top performers this year:",
                 stats=[stat("School average", f"{d['avg_pct']}%", _tone(d["avg_pct"]))],
                 bars=[bar(f"{x['name']} ({x['grade']}-{x['section']})", x["pct"]) for x in d["top_students"]],
                 actions=_who_buttons(d["top_students"]))

    if _has(q, "at risk", "at-risk", "failing", "weak students", "low performing", "struggling"):
        if not can_students:
            return R(DENIED)
        d = analytics.dashboard(db, sid, CURRENT_YEAR)
        if not d["at_risk"]:
            return R("No students are currently below the 50% benchmark.", stats=[stat("At risk", 0, "good")])
        return R("Students who need support (below 50%):",
                 stats=[stat("At risk", len(d["at_risk"]), "bad"), stat("School average", f"{d['avg_pct']}%", _tone(d["avg_pct"]))],
                 bars=[bar(f"{x['name']} ({x['grade']}-{x['section']})", x["pct"]) for x in d["at_risk"]],
                 actions=_who_buttons(d["at_risk"]))

    if _has(q, "how many", "count", "total", "number of") and _has(q, "teacher", "staff", "faculty"):
        n = db.scalar(select(func.count()).select_from(Staff).where(Staff.school_id == sid))
        return R(f"The school has {n} staff members.", stats=[stat("Staff", n)], actions=[act("Open staff", "/staff")])

    if _has(q, "how many", "count", "total", "number of", "strength") and _has(q, "student", "pupil", "children", "kids", "strength"):
        stmt = select(func.count()).select_from(Student).where(Student.school_id == sid)
        if grade:
            n = db.scalar(stmt.where(Student.grade == grade))
            return R(f"Class {grade} has {n} students.", stats=[stat("Students", n)],
                     actions=[act("View students", f"/students?grade={grade}")] if not is_student else [])
        n = db.scalar(stmt)
        return R(f"The school has {n} students across LKG to 10th.", stats=[stat("Students", n)],
                 actions=[act("View students", "/students")])

    if _has(q, "event", "upcoming", "function", "celebration", "sports day", "annual day"):
        ev = db.scalars(select(Event).where(Event.school_id == sid, Event.date >= date.today())
                        .order_by(Event.date).limit(5)).all()
        lead = "Upcoming events"
        if not ev:
            ev = db.scalars(select(Event).where(Event.school_id == sid).order_by(Event.date.desc()).limit(5)).all()
            lead = "No upcoming events. Most recent"
        if not ev:
            return R("No events have been added yet.")
        return R(lead + ":\n" + "\n".join(f"• {e.title} — {e.date.strftime('%d %b %Y')}, {e.location}" for e in ev),
                 stats=[stat("Events", len(ev))], actions=[act("Open events", "/events")])

    if _has(q, "goal", "future", "vision", "plan", "roadmap"):
        gs = db.scalars(select(Goal).where(Goal.school_id == sid).order_by(Goal.target_year)).all()
        if not gs:
            return R("No future goals have been added yet.")
        return R("Future goals and progress:", bars=[bar(f"{g.title} ({g.target_year})", g.progress) for g in gs],
                 actions=[act("Open goals", "/goals")])

    if _has(q, "about", "school", "mission", "history", "founded", "address", "principal"):
        sc = db.get(School, sid)
        txt = "\n\n".join(filter(None, [sc.name, sc.about, sc.mission, sc.vision,
                                         f"Address: {sc.address}" if sc.address else None]))
        return R(txt or "About information is not set up yet.", actions=[act("About school", "/about")])

    if _has(q, "subject"):
        return R("Which class? For example: \"Which subjects does class 8 have?\"", actions=[act("Open subjects", "/subjects")])

    return R("I can answer about students, marks, fees, staff, subjects, chapters, events, goals and the school. "
             "Try one of the suggestions below.")


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


HISTORY_LIMIT = 200


def suggestions_for(user: User) -> list[str]:
    return STUDENT_SUGGESTIONS if user.role == "student" else (STAFF_SUGGESTIONS if perm_set(user) else SUGGESTIONS)


def history(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(AssistantMessage).where(AssistantMessage.user_id == user.id)
                      .order_by(AssistantMessage.id.desc()).limit(HISTORY_LIMIT)).all()[::-1]
    return [{"id": m.id, "who": m.who, "text": m.text, "at": m.created_at.isoformat() + "Z", **(m.extra or {})} for m in rows]


def clear_history(db: Session, user: User) -> None:
    db.execute(delete(AssistantMessage).where(AssistantMessage.user_id == user.id))
    db.commit()


def ask(db: Session, user: User, question: str) -> dict:
    question = question.strip()[:MAX_Q]
    reply = answer_rules(db, user, question)
    phrased = _llm_rephrase(question, reply["text"]) if reply["text"] != DENIED else None
    text = phrased or reply["text"]
    extra = {k: reply[k] for k in ("stats", "bars", "actions") if reply[k]}
    db.add(AssistantMessage(user_id=user.id, who="me", text=question))
    db.add(AssistantMessage(user_id=user.id, who="bot", text=text, extra=extra or None))
    db.commit()
    # keep only the most recent messages
    cutoff = db.scalar(select(AssistantMessage.id).where(AssistantMessage.user_id == user.id)
                       .order_by(AssistantMessage.id.desc()).offset(HISTORY_LIMIT).limit(1))
    if cutoff:
        db.execute(delete(AssistantMessage).where(AssistantMessage.user_id == user.id, AssistantMessage.id <= cutoff))
        db.commit()
    return {"answer": text, "stats": reply["stats"], "bars": reply["bars"], "actions": reply["actions"],
            "source": "llm" if phrased else "database", "suggestions": suggestions_for(user)}
