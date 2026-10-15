"""Smart import: hand over a school's existing data (xlsx / csv / json / docx) and have it loaded safely.

Flow: upload -> the file is read and each sheet is classified and its columns mapped -> the user reviews and corrects
the mapping -> a dry run reports exactly what would be created / matched / rejected -> confirm. Nothing is written
until the user confirms, the confirm is all-or-nothing, and every confirmed import can be undone for 7 days.
The dry run and the real run share one code path (the dry run is rolled back), so what you review is what you get."""
import logging
import re
import secrets
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import smartimport as si
from .. import storage
from ..db import get_db
from ..deps import make_code, next_code, staff_letter, year_of
from ..models import (EXAM_MAX, GRADES, Chapter, Event, Fee, Goal, ImportBatch, ImportJob, Mark, Payment, School, Staff,
                      Student, Subject, User)
from ..schemas import YEAR, EventIn, GoalIn, StaffIn, StudentIn, SubjectIn
from ..security import PRINCIPAL_DEFAULT, TEACHER_DEFAULT, gen_password, hash_password, need, perm_set, rate_limit
from ..smartimport import KIND_ORDER, KINDS, ImportFileError, canon_subject, norm_exam, norm_name, norm_year, parse_date
from .bulk import BULK_BCRYPT_ROUNDS, _clean, _gender, _grade

log = logging.getLogger("school.import")
router = APIRouter(prefix="/api/import")

UNDO_DAYS = 7
JOB_HOURS = 24
MAX_JOBS_PER_USER = 5
ERRORS_SHOWN = 100
ANY_IMPORT = tuple(sorted({k["perm"] for k in KINDS.values()}))
ABSENT = {"", "ab", "absent", "na", "n/a", "nil", "-", "--", "x"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------- request models ----------
class SheetCfg(BaseModel):
    index: int = Field(ge=0, le=100)
    include: bool = True
    kind: str = Field(max_length=20)
    header_row: int = Field(ge=0, le=9)
    mapping: dict[str, int] = Field(default_factory=dict, max_length=40)
    on_duplicate: Literal["skip", "update"] = "skip"  # only marks and fees can be updated
    year: Optional[str] = Field(default=None, pattern=YEAR)
    exam: Optional[Literal["UT1", "Midterm", "UT2", "Final"]] = None
    mode: Literal["Cash", "UPI", "Card", "Cheque", "Bank Transfer"] = "Cash"


class RunIn(BaseModel):
    sheets: list[SheetCfg] = Field(max_length=25)
    create_logins: bool = True
    create_subjects: bool = False


# ---------- small helpers ----------
def _v(row: list, mapping: dict, field: str) -> str:
    i = mapping.get(field)
    return row[i].strip() if i is not None and i < len(row) else ""


def _msg(e: ValidationError) -> str:
    return "; ".join(f"{(x['loc'][-1] if x['loc'] else 'row')}: {x['msg'].removeprefix('Value error, ')}" for x in e.errors())


def _num(v: str) -> Optional[float]:
    """'1,200.50', 'Rs. 5000' -> float. Blank -> None. Anything else that is not a number raises ValueError."""
    if not v or not v.strip():
        return None
    s = re.sub(r"(?i)rs\.?|inr|\u20b9|,|\s", "", v)
    return float(s)


def _class_section(v: str) -> tuple[str, str]:
    """'5A', '5-A', 'LKG B' -> ('5', 'A'). A plain class comes back with an empty section."""
    g = _grade(v)
    m = re.fullmatch(r"(\d{1,2}|lkg|ukg)[-/]?([a-z])", re.sub(r"\s+", "", g), re.I)
    return (_grade(m[1]), m[2].upper()) if m else (g, "")


def _phone(v: str) -> str:
    return re.sub(r"[().]", "", v).strip()


class Rep:
    """Per-sheet findings."""

    def __init__(self, cfg: SheetCfg, sheet_name: str):
        self.d = {"index": cfg.index, "name": sheet_name, "kind": cfg.kind, "label": KINDS[cfg.kind]["label"], "rows": 0,
                  "new": 0, "matched": 0, "updated": 0, "skipped": 0, "error_count": 0, "errors": [], "warnings": [],
                  "conflicts": []}
        self._notes: dict = {}

    def err(self, row: int, who: str, msg: str) -> None:
        self.d["error_count"] += 1
        if len(self.d["errors"]) < ERRORS_SHOWN:
            self.d["errors"].append({"row": row, "name": (who or "")[:60], "message": msg})

    def note(self, key: str, text: str) -> None:
        n = self._notes.setdefault(key, [text, 0])
        n[1] += 1

    def conflict(self, text: str) -> None:
        if len(self.d["conflicts"]) < 10:
            self.d["conflicts"].append(text)

    def finish(self) -> dict:
        self.d["warnings"] = [f"{n} row(s): {t}" for t, n in self._notes.values()]
        return self.d


class Ctx:
    """Everything one run needs: indexes of what the school already has, plus what this run adds."""

    def __init__(self, db: Session, user: User, body: RunIn, commit: bool):
        self.db, self.user, self.sid, self.commit = db, user, user.school_id, commit
        self.logins, self.create_subjects = body.create_logins, body.create_subjects
        self.year = year_of(db, self.sid)
        self.counters: dict = {}
        self.new: dict = defaultdict(list)
        self.updated: dict = defaultdict(dict)
        self.pending: list = []
        self.blockers: list = []
        self.by_legacy, self.by_key, self.by_name = {}, {}, defaultdict(list)
        students = list(db.scalars(select(Student).where(Student.school_id == self.sid)))
        self.students_before = len(students)
        for s in students:
            if s.legacy_id:
                self.by_legacy.setdefault(s.legacy_id.lower(), s)
        for s in students:
            self.index_student(s)
        self.subjects: dict = {}
        for sub in db.scalars(select(Subject).where(Subject.school_id == self.sid)):
            self.subjects.setdefault((sub.grade, canon_subject(sub.name)), sub)
        self.staff_legacy, self.staff_np, self.staff_ne = {}, {}, {}
        staff = list(db.scalars(select(Staff).where(Staff.school_id == self.sid)))
        self.staff_before = len(staff)
        for t in staff:
            self.index_staff(t)
        self.marks: dict = {}
        self.fees: dict = {}
        self.pays: dict = {}
        self.fresh: set = set()  # id() of marks / fees created in this run
        self.consumed: set = set()  # ids of existing payments already matched by a row
        self.entries = 0
        self.event_keys: Optional[set] = None
        self.goal_keys: Optional[set] = None

    # --- student / staff indexes ---
    def index_student(self, s: Student) -> None:
        self.by_legacy.setdefault(s.admission_no.lower(), s)
        if s.legacy_id:
            self.by_legacy.setdefault(s.legacy_id.lower(), s)
        self.by_key[(norm_name(s.name), s.dob, s.grade)] = s
        self.by_name[norm_name(s.name)].append(s)

    def index_staff(self, t: Staff) -> None:
        if t.legacy_id:
            self.staff_legacy.setdefault(t.legacy_id.lower(), t)
        self.staff_legacy.setdefault(t.employee_id.lower(), t)
        self.staff_np[(norm_name(t.name), re.sub(r"\D", "", t.phone)[-10:])] = t
        self.staff_ne[(norm_name(t.name), t.email.lower())] = t

    def alloc(self, letter: str, grade: Optional[str] = None) -> str:
        """Next free ID. Asks the database once per series, then counts up in memory."""
        k = (letter, grade)
        if k not in self.counters:
            code = next_code(self.db, self.sid, letter, grade)
            self.counters[k] = int(code[-3:])
            return code
        n = self.counters[k] + 1
        if n > 999:
            raise HTTPException(409, "No numbers left for this ID series")
        self.counters[k] = n
        return make_code(self.sid, letter, n, grade)

    def snap(self, table: str, obj_id: int, col: str, old, new) -> None:
        """Remember [old, new] of a value this import changed, so undo can put it back (only if it still holds `new`)."""
        e = self.updated[table].setdefault(str(obj_id), {}).setdefault(col, [old, new])
        e[1] = new

    # --- lazily loaded per-student data ---
    def marks_of(self, sid: int) -> dict:
        if sid not in self.marks:
            self.marks[sid] = {(m.subject_id, m.exam, m.academic_year): m
                               for m in self.db.scalars(select(Mark).where(Mark.student_id == sid))}
        return self.marks[sid]

    def fee_of(self, sid: int, year: str) -> Optional[Fee]:
        if (sid, year) not in self.fees:
            self.fees[(sid, year)] = self.db.scalar(select(Fee).where(Fee.student_id == sid, Fee.academic_year == year))
        return self.fees[(sid, year)]

    def pays_of(self, sid: int, year: str) -> list:
        if (sid, year) not in self.pays:
            self.pays[(sid, year)] = [[p, False] for p in self.db.scalars(
                select(Payment).where(Payment.student_id == sid, Payment.academic_year == year))]
        return self.pays[(sid, year)]

    def paid(self, sid: int, year: str) -> float:
        return round(sum(p.amount for p, _ in self.pays_of(sid, year)), 2)

    def add_payment(self, sid: int, year: str, amount: float, when: date, mode: str) -> None:
        p = Payment(student_id=sid, academic_year=year, amount=round(amount, 2), paid_on=when, mode=mode,
                    receipt_no=f"IMP-{secrets.token_hex(5).upper()}")
        self.db.add(p)
        self.pays_of(sid, year).append([p, True])
        self.new["payments"].append(p)

    def add_login(self, user_obj: User, info: dict) -> None:
        if self.commit and self.logins:  # added to the session only after its password is hashed (see run())
            self.pending.append((user_obj, gen_password(), info))


def _rows(sh: si.Sheet, cfg: SheetCfg):
    for i in range(cfg.header_row + 1, len(sh.rows)):
        if any(sh.rows[i]):
            yield i + 1, sh.rows[i]  # the row number as the spreadsheet shows it


# ---------- subjects, students, staff ----------
def do_subjects(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        name = " ".join(_v(row, m, "name").split())
        try:
            s = SubjectIn(name=name, grade=_grade(_v(row, m, "grade")))
        except ValidationError as e:
            rep.err(rown, name, _msg(e))
            continue
        if (s.grade, canon_subject(s.name)) in ctx.subjects:
            rep.d["matched"] += 1
            continue
        sub = Subject(school_id=ctx.sid, name=s.name, grade=s.grade)
        ctx.db.add(sub)
        ctx.db.flush()
        ctx.subjects[(s.grade, canon_subject(s.name))] = sub
        ctx.new["subjects"].append(sub)
        rep.d["new"] += 1


def do_students(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    seen_legacy: dict = {}
    seen_key: set = set()
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        raw = {f: _v(row, m, f) for f in KINDS["students"]["fields"]}
        legacy = raw.pop("legacy_id")
        raw["name"], raw["phone"] = " ".join(raw["name"].split()), _phone(raw["phone"])
        if not raw["section"]:
            raw["grade"], raw["section"] = _class_section(raw["grade"])
            if not raw["section"]:
                raw["section"] = "A"
                rep.note("section", "no section given, used A")
        if len(legacy) > 40:
            rep.err(rown, raw["name"], "The old ID is longer than 40 characters")
            continue
        try:
            s = StudentIn(**_clean(raw))
        except ValidationError as e:
            rep.err(rown, raw["name"], _msg(e))
            continue
        key = (norm_name(s.name), s.dob, s.grade)
        lk = legacy.lower()
        if lk and lk in seen_legacy and seen_legacy[lk][:3] != key:
            rep.err(rown, s.name, f"ID {legacy} is already used by a different student in row {seen_legacy[lk][3]}")
            continue
        if key in seen_key:
            rep.d["skipped"] += 1
            rep.note("repeat", "the same student appears again in this sheet, counted once")
            continue
        seen_key.add(key)
        if lk:
            seen_legacy[lk] = key + (rown,)
        found = ctx.by_legacy.get(lk) if lk else None
        if found and found.dob != s.dob and norm_name(found.name) != key[0]:
            rep.err(rown, s.name, f"ID {legacy} already belongs to another student ({found.name})")
            continue
        found = found or ctx.by_key.get(key)
        if found:
            rep.d["matched"] += 1
            if lk and not found.legacy_id and lk not in ctx.by_legacy:  # remember the old ID so marks and fees can find them
                ctx.snap("students", found.id, "legacy_id", None, legacy)
                found.legacy_id = legacy
                ctx.by_legacy[lk] = found
            continue
        st = Student(school_id=ctx.sid, admission_no=ctx.alloc("s", s.grade), legacy_id=legacy or None,
                     **s.model_dump(exclude={"admission_no"}))
        ctx.db.add(st)
        ctx.db.flush()
        ctx.index_student(st)
        ctx.new["students"].append(st)
        rep.d["new"] += 1
        ctx.add_login(User(school_id=ctx.sid, username=st.admission_no, password_hash="!", role="student",
                           full_name=st.name, student_id=st.id, must_change=True),
                      {"login": st.admission_no, "name": st.name, "role": "Student", "class": f"{st.grade}-{st.section}"})


def do_staff(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        raw = {f: _v(row, m, f) for f in KINDS["staff"]["fields"]}
        name = " ".join(raw["name"].split())
        legacy = raw["legacy_id"]
        if len(legacy) > 40:
            rep.err(rown, name, "The old ID is longer than 40 characters")
            continue
        try:
            exp = int(_num(raw["experience_years"]) or 0)
        except ValueError:
            rep.err(rown, name, "experience_years: not a number")
            continue
        joined = parse_date(raw["joined_on"]) if raw["joined_on"] else date.today()
        if not joined:
            rep.err(rown, name, "joined_on: not a recognised date")
            continue
        if not raw["joined_on"]:
            rep.note("joined", "no joining date, used today")
        if not raw["department"] or not raw["qualification"]:
            rep.note("defaults", "no department / qualification given, filled with 'General' / 'Not provided'")
        try:
            s = StaffIn(name=name, gender=_gender(raw["gender"]), designation=" ".join(raw["designation"].split()),
                        department=raw["department"] or "General", qualification=raw["qualification"] or "Not provided",
                        experience_years=exp, subjects=raw["subjects"] or None, class_teacher_of=raw["class_teacher_of"] or None,
                        phone=_phone(raw["phone"]), email=raw["email"], joined_on=joined, bio=raw["bio"] or None)
        except ValidationError as e:
            rep.err(rown, name, _msg(e))
            continue
        nn = norm_name(s.name)
        found = (ctx.staff_legacy.get(legacy.lower()) if legacy else None) \
            or ctx.staff_np.get((nn, re.sub(r"\D", "", s.phone)[-10:])) or ctx.staff_ne.get((nn, s.email.lower()))
        if found:
            rep.d["matched"] += 1
            continue
        letter = staff_letter(s.designation)
        st = Staff(school_id=ctx.sid, employee_id=ctx.alloc(letter), legacy_id=legacy or None,
                   **s.model_dump(exclude={"employee_id"}))
        ctx.db.add(st)
        ctx.db.flush()
        ctx.index_staff(st)
        ctx.new["staff"].append(st)
        rep.d["new"] += 1
        granted = sorted(set(PRINCIPAL_DEFAULT if letter == "p" else TEACHER_DEFAULT) & perm_set(ctx.user))
        ctx.add_login(User(school_id=ctx.sid, username=st.employee_id, password_hash="!", role="staff", full_name=st.name,
                           permissions=",".join(granted), staff_id=st.id, must_change=True),
                      {"login": st.employee_id, "name": st.name, "role": st.designation, "class": ""})



# ---------- finding the student a marks / fees row is about ----------
def find_student(ctx: Ctx, row: list, m: dict, rep: Rep, rown: int) -> Optional[Student]:
    sid_txt, name = _v(row, m, "student_id"), " ".join(_v(row, m, "name").split())
    who = name or sid_txt
    if sid_txt:
        s = ctx.by_legacy.get(sid_txt.lower())
        if s:
            return s
        if not name:
            rep.err(rown, who, f"No student with ID {sid_txt}. Import the students first, or check the ID")
            return None
    if not name:
        rep.err(rown, "", "Neither a student ID nor a name is given")
        return None
    cands = ctx.by_name.get(norm_name(name), [])
    grade, section = _v(row, m, "grade"), _v(row, m, "section")
    if grade:
        if not section:
            g, section = _class_section(grade)
        else:
            g = _grade(grade)
        cands = [c for c in cands if c.grade == g]
    if section:
        cands = [c for c in cands if c.section == section.strip().upper()[:1]]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        rep.err(rown, who, "No matching student found" + (" (check the ID, name or class)" if sid_txt else ". Add the student ID or class to match them"))
    else:
        rep.err(rown, who, f"{len(cands)} students match this name. Add the student ID or class and section to tell them apart")
    return None


def _year(ctx: Ctx, row, cfg: SheetCfg, rep: Rep, rown: int, who: str) -> Optional[str]:
    raw = _v(row, cfg.mapping, "year")
    if raw:
        y = norm_year(raw)
        if not y:
            rep.err(rown, who, f"year: '{raw}' is not an academic year like 2025-26")
        return y
    if cfg.year:
        return cfg.year
    rep.note("year", f"no academic year given, used {ctx.year}")
    return ctx.year


# ---------- marks ----------
def do_marks(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        stu = find_student(ctx, row, m, rep, rown)
        if not stu:
            continue
        who = stu.name
        raw_score = _v(row, m, "score")
        if raw_score.strip().lower() in ABSENT:
            rep.d["skipped"] += 1
            rep.note("absent", "no marks (blank or absent), skipped")
            continue
        try:
            score, mx_given = _num(raw_score), _num(_v(row, m, "max"))
        except ValueError:
            rep.err(rown, who, f"score: '{raw_score}' is not a number")
            continue
        exam_txt = _v(row, m, "exam")
        exam = norm_exam(exam_txt) if exam_txt else cfg.exam
        if not exam:
            rep.err(rown, who, f"exam: '{exam_txt}' is not one of UT1, Midterm, UT2, Final" if exam_txt else "No exam given for this row")
            continue
        year = _year(ctx, row, cfg, rep, rown, who)
        if not year:
            continue
        mx = EXAM_MAX[exam]
        if mx_given is not None and mx_given > 0 and mx_given != mx:
            score = round(score * mx / mx_given, 2)
            rep.note("scaled", f"marks were out of a different maximum, scaled to the school's maximum for that exam")
        if score < 0 or score > mx:
            rep.err(rown, who, f"score {score:g} is outside 0-{mx} for {exam}")
            continue
        subj_txt = " ".join(_v(row, m, "subject").split())
        sub = ctx.subjects.get((stu.grade, canon_subject(subj_txt)))
        if not sub:
            if not (ctx.create_subjects and 2 <= len(subj_txt) <= 80):
                rep.err(rown, who, f"Class {stu.grade} has no subject '{subj_txt}'. Import the subjects first, or allow new subjects to be created")
                continue
            sub = Subject(school_id=ctx.sid, name=subj_txt, grade=stu.grade)
            ctx.db.add(sub)
            ctx.db.flush()
            ctx.subjects[(stu.grade, canon_subject(subj_txt))] = sub
            ctx.new["subjects"].append(sub)
            rep.note("newsubj", "created a subject that did not exist")
        marks = ctx.marks_of(stu.id)
        key = (sub.id, exam, year)
        cur = marks.get(key)
        if cur is None:
            mk = Mark(student_id=stu.id, subject_id=sub.id, exam=exam, academic_year=year, score=score, max_score=mx)
            ctx.db.add(mk)
            marks[key] = mk
            ctx.fresh.add(id(mk))
            ctx.new["marks"].append(mk)
            rep.d["new"] += 1
        elif id(cur) in ctx.fresh:
            if cur.score != score:
                rep.err(rown, who, f"{sub.name} {exam} {year} appears twice in the file with different marks ({cur.score:g} and {score:g})")
            else:
                rep.d["skipped"] += 1
        elif cur.score == score:
            rep.d["matched"] += 1
        elif cfg.on_duplicate == "update":
            ctx.snap("marks", cur.id, "score", cur.score, score)
            cur.score = score
            rep.d["updated"] += 1
        else:
            rep.d["matched"] += 1
            rep.conflict(f"{who}: {sub.name} {exam} {year} is {cur.score:g} in the system but {score:g} in the file (kept the system value)")


# ---------- fees and payments ----------
def _paid_on(row, m, rep: Rep, rown: int, who: str) -> Optional[date]:
    raw = _v(row, m, "paid_on")
    if not raw:
        rep.note("paidon", "no payment date, used today")
        return date.today()
    d = parse_date(raw)
    if not d or d > date.today():
        rep.err(rown, who, f"paid_on: '{raw}' is not a valid past date")
        return None
    return d


def _mode(row, m, cfg: SheetCfg) -> str:
    return si.PAY_MODES.get(" ".join(_v(row, m, "mode").lower().split()), cfg.mode)


def do_fees(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        stu = find_student(ctx, row, m, rep, rown)
        if not stu:
            continue
        who = stu.name
        try:
            total, paid = _num(_v(row, m, "total_amount")), _num(_v(row, m, "paid"))
        except ValueError:
            rep.err(rown, who, "The fee or the amount paid is not a number")
            continue
        if total is None or total < 0 or total > 10_000_000 or (paid is not None and paid < 0):
            rep.err(rown, who, "The total fee must be between 0 and 10,000,000")
            continue
        year = _year(ctx, row, cfg, rep, rown, who)
        if not year:
            continue
        fee = ctx.fee_of(stu.id, year)
        if fee is None:
            fee = Fee(student_id=stu.id, academic_year=year, total_amount=total)
            ctx.db.add(fee)
            ctx.fees[(stu.id, year)] = fee
            ctx.fresh.add(id(fee))
            ctx.new["fees"].append(fee)
            rep.d["new"] += 1
        elif id(fee) in ctx.fresh:
            if fee.total_amount != total:
                rep.err(rown, who, f"{year} fee appears twice in the file with different totals")
                continue
            rep.d["skipped"] += 1
        elif fee.total_amount == total:
            rep.d["matched"] += 1
        elif cfg.on_duplicate == "update":
            ctx.snap("fees", fee.id, "total_amount", fee.total_amount, total)
            fee.total_amount = total
            rep.d["updated"] += 1
        else:
            rep.d["matched"] += 1
            rep.conflict(f"{who}: {year} fee is {fee.total_amount:g} in the system but {total:g} in the file (kept the system value)")
        if paid:
            if paid > fee.total_amount:
                rep.err(rown, who, f"The amount paid ({paid:g}) is more than the total fee ({fee.total_amount:g})")
                continue
            have = ctx.paid(stu.id, year)
            if paid > have + 0.005:  # only the difference is recorded, so importing the same file again adds nothing
                when = _paid_on(row, m, rep, rown, who)
                if when is None:
                    continue
                ctx.add_payment(stu.id, year, paid - have, when, _mode(row, m, cfg))
                rep.note("paiddiff", "payments recorded for the amount paid that the system did not have yet")
            elif paid < have - 0.005:
                rep.note("paidless", "the system already records more as paid than the file says, left unchanged")


def do_payments(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        stu = find_student(ctx, row, m, rep, rown)
        if not stu:
            continue
        who = stu.name
        try:
            amount = _num(_v(row, m, "amount"))
        except ValueError:
            rep.err(rown, who, "amount: not a number")
            continue
        if amount is None or not 0 < amount <= 10_000_000:
            rep.err(rown, who, "amount: must be more than 0 and at most 10,000,000")
            continue
        year = _year(ctx, row, cfg, rep, rown, who)
        if not year:
            continue
        when = _paid_on(row, m, rep, rown, who)
        if when is None:
            continue
        for entry in ctx.pays_of(stu.id, year):  # the same payment already in the system?
            p, is_new = entry
            if not is_new and p.id not in ctx.consumed and abs(p.amount - amount) < 0.005 and p.paid_on == when:
                ctx.consumed.add(p.id)
                rep.d["matched"] += 1
                break
        else:
            fee = ctx.fee_of(stu.id, year)
            if fee is None:
                rep.err(rown, who, f"No fee is set for {year}. Import the fees first")
                continue
            if ctx.paid(stu.id, year) + amount > fee.total_amount + 0.005:
                rep.err(rown, who, f"This payment would take the total paid past the {year} fee of {fee.total_amount:g}")
                continue
            ctx.add_payment(stu.id, year, amount, when, _mode(row, m, cfg))
            rep.d["new"] += 1


# ---------- events and goals ----------
def do_events(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    if ctx.event_keys is None:
        ctx.event_keys = {(norm_name(e.title), e.date) for e in ctx.db.scalars(select(Event).where(Event.school_id == ctx.sid))}
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        title = " ".join(_v(row, m, "title").split())
        when = parse_date(_v(row, m, "date"))
        if not when:
            rep.err(rown, title, "date: not a recognised date")
            continue
        try:
            e = EventIn(title=title, description=_v(row, m, "description") or title, date=when,
                        location=_v(row, m, "location") or "School", category=_v(row, m, "category") or "General")
        except ValidationError as ex:
            rep.err(rown, title, _msg(ex))
            continue
        key = (norm_name(e.title), e.date)
        if key in ctx.event_keys:
            rep.d["matched"] += 1
            continue
        ctx.event_keys.add(key)
        ev = Event(school_id=ctx.sid, **e.model_dump())
        ctx.db.add(ev)
        ctx.new["events"].append(ev)
        rep.d["new"] += 1


def do_goals(ctx: Ctx, sh, cfg, rep: Rep, body: RunIn) -> None:
    m = cfg.mapping
    if ctx.goal_keys is None:
        ctx.goal_keys = {(norm_name(g.title), g.target_year) for g in ctx.db.scalars(select(Goal).where(Goal.school_id == ctx.sid))}
    for rown, row in _rows(sh, cfg):
        rep.d["rows"] += 1
        title = " ".join(_v(row, m, "title").split())
        try:
            year, prog = int(_num(_v(row, m, "target_year")) or 0), int(_num(_v(row, m, "progress").rstrip("%")) or 0)
        except ValueError:
            rep.err(rown, title, "target_year or progress: not a number")
            continue
        status = {"planned": "Planned", "in progress": "In Progress", "ongoing": "In Progress", "completed": "Completed",
                  "done": "Completed"}.get(_v(row, m, "status").lower(), "Completed" if prog >= 100 else "In Progress" if prog else "Planned")
        try:
            g = GoalIn(title=title, description=_v(row, m, "description") or title, target_year=year, progress=prog, status=status)
        except ValidationError as ex:
            rep.err(rown, title, _msg(ex))
            continue
        key = (norm_name(g.title), g.target_year)
        if key in ctx.goal_keys:
            rep.d["matched"] += 1
            continue
        ctx.goal_keys.add(key)
        go = Goal(school_id=ctx.sid, **g.model_dump())
        ctx.db.add(go)
        ctx.new["goals"].append(go)
        rep.d["new"] += 1


HANDLERS = {"subjects": do_subjects, "students": do_students, "staff": do_staff, "fees": do_fees, "payments": do_payments,
            "marks": do_marks, "events": do_events, "goals": do_goals}
# a sheet of this kind needs (student_id or name) as well as the fields marked required
NEEDS_STUDENT = {"marks", "fees", "payments"}
CREATED_PERM = {"students": "students.manage", "staff": "staff.manage", "subjects": "subjects.manage", "marks": "marks.edit",
                "fees": "fees.manage", "payments": "fees.manage", "events": "content.manage", "goals": "content.manage"}


def _missing(cfg: SheetCfg) -> list[str]:
    fields = KINDS[cfg.kind]["fields"]
    miss = [fields[f][0] for f, (_, req, _) in fields.items() if req and f not in cfg.mapping]
    if cfg.kind in NEEDS_STUDENT and not ({"student_id", "name"} & set(cfg.mapping)):
        miss.append("Student ID or Student name")
    if cfg.kind == "marks":
        if "subject" not in cfg.mapping:
            miss.append("Subject")
        if "score" not in cfg.mapping:
            miss.append("Marks obtained")
        if "exam" not in cfg.mapping and not cfg.exam:
            miss.append("Exam / test (or choose one exam for the whole sheet)")
    return miss


def _load(db: Session, user: User, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if not job or job.school_id != user.school_id or job.user_id != user.id or job.created_at < _now() - timedelta(hours=JOB_HOURS):
        raise HTTPException(404, "That upload was not found or has expired. Upload the file again")
    return job


def _execute(db: Session, user: User, job: ImportJob, body: RunIn, commit: bool) -> tuple[dict, Ctx]:
    try:
        sheets = si.read_file(job.data)
    except ImportFileError as e:
        raise HTTPException(422, str(e))
    if body.create_subjects and "subjects.manage" not in perm_set(user):
        raise HTTPException(403, "You do not have permission to create subjects")
    if len({c.index for c in body.sheets}) != len(body.sheets):
        raise HTTPException(422, "A sheet was listed twice")
    perms = perm_set(user)
    chosen = [c for c in body.sheets if c.include]
    for c in chosen:
        if c.kind not in KINDS or c.index >= len(sheets):
            raise HTTPException(422, "Unknown sheet or data type")
        if KINDS[c.kind]["perm"] not in perms:
            raise HTTPException(403, f"You do not have permission to import {KINDS[c.kind]['label'].lower()}")
        sh = sheets[c.index]
        if c.header_row >= len(sh.rows):
            raise HTTPException(422, "The heading row is outside the sheet")
        width = len(sh.rows[c.header_row])
        for f, i in c.mapping.items():
            if f not in KINDS[c.kind]["fields"] or not 0 <= i < width:
                raise HTTPException(422, "A column choice is not valid")
        if len(set(c.mapping.values())) != len(c.mapping):
            raise HTTPException(422, f"In sheet '{sh.name}' one column is chosen for two different fields")
    if not chosen:
        raise HTTPException(422, "Choose at least one sheet to import")
    ctx = Ctx(db, user, body, commit)
    reps = []
    for c in sorted(chosen, key=lambda c: KIND_ORDER.index(c.kind)):
        sh = sheets[c.index]
        rep = Rep(c, sh.name)
        miss = _missing(c)
        if miss:
            ctx.blockers.append(f"Sheet '{sh.name}': choose a column for {', '.join(miss)}")
        else:
            HANDLERS[c.kind](ctx, sh, c, rep, body)
        reps.append(rep.finish())
    school = db.get(School, user.school_id)
    n_stu, n_staff = len(ctx.new["students"]), len(ctx.new["staff"])
    if ctx.students_before + n_stu > school.max_students:
        ctx.blockers.append(f"Your plan allows at most {school.max_students} student records ({ctx.students_before} now, {n_stu} would be added). Contact the platform team to raise it")
    if ctx.staff_before + n_staff > school.max_staff:
        ctx.blockers.append(f"Your plan allows at most {school.max_staff} staff records ({ctx.staff_before} now, {n_staff} would be added). Contact the platform team to raise it")
    errors = sum(r["error_count"] for r in reps)
    changes = sum(len(v) for v in ctx.new.values()) + sum(len(v) for v in ctx.updated.values())
    report = {"sheets": reps, "blockers": ctx.blockers, "errors": errors, "changes": changes,
              "totals": {k: len(v) for k, v in ctx.new.items() if v}, "updated": {k: len(v) for k, v in ctx.updated.items() if v},
              "logins": (n_stu + n_staff) if body.create_logins else 0,
              "can_confirm": errors == 0 and not ctx.blockers}
    return report, ctx


# ---------- endpoints ----------
def _kinds_for(user: User) -> dict:
    perms = perm_set(user)
    return {k: {"label": v["label"], "allowed": v["perm"] in perms,
                "fields": [{"key": f, "label": lab, "required": req} for f, (lab, req, _) in v["fields"].items()]}
            for k, v in KINDS.items()}


def _analysis(user: User, sheets: list) -> list:
    out = []
    for i, sh in enumerate(sheets):
        a = si.analyse(sh)
        a.update(index=i, name=sh.name, suggested_by="rules" if a["kind"] else None)
        out.append(a)
    weak = [{"index": a["index"], "name": a["name"], "headers": a["headers"]} for a in out
            if not a["kind"] or any(req and f not in a["mapping"] for f, (_, req, _) in KINDS[a["kind"]]["fields"].items())]
    for idx, sug in si.llm_suggest(weak).items():
        a = out[idx]
        if not a["kind"]:
            a.update(kind=sug["kind"], mapping=sug["mapping"], suggested_by="ai")
        elif a["kind"] == sug["kind"]:
            used = set(a["mapping"].values())
            for f, i in sug["mapping"].items():
                if f not in a["mapping"] and i not in used:
                    a["mapping"][f] = i
                    used.add(i)
    return out


@router.post("/upload", status_code=201)
async def upload(request: Request, filename: str = Query("upload", max_length=120),
                 user: User = Depends(need(*ANY_IMPORT)), db: Session = Depends(get_db)):
    rate_limit(f"smartimport:{user.id}", 30)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > si.MAX_FILE:
        raise HTTPException(413, "File too large (max 5 MB)")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > si.MAX_FILE:
            raise HTTPException(413, "File too large (max 5 MB)")
    data = bytes(buf)
    try:
        sheets = await run_in_threadpool(si.read_file, data)
    except ImportFileError as e:
        raise HTTPException(422, str(e))
    analysis = await run_in_threadpool(_analysis, user, sheets)
    db.execute(delete(ImportJob).where(ImportJob.created_at < _now() - timedelta(hours=JOB_HOURS)))
    mine = list(db.scalars(select(ImportJob.id).where(ImportJob.user_id == user.id).order_by(ImportJob.id.desc())))
    if len(mine) >= MAX_JOBS_PER_USER:  # keep the newest few uploads only
        db.execute(delete(ImportJob).where(ImportJob.id.in_(mine[MAX_JOBS_PER_USER - 1:])))
    name = re.sub(r"[^\w .()-]", "_", filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:120] or "upload"
    job = ImportJob(school_id=user.school_id, user_id=user.id, filename=name, data=data)
    db.add(job)
    db.commit()
    return {"job_id": job.id, "filename": name, "sheets": analysis, "kinds": _kinds_for(user), "ai": si.llm_enabled(),
            "year": year_of(db, user.school_id), "expires_hours": JOB_HOURS}


@router.delete("/jobs/{job_id}", status_code=204)
def cancel(job_id: int, user: User = Depends(need(*ANY_IMPORT)), db: Session = Depends(get_db)):
    db.delete(_load(db, user, job_id))
    db.commit()


@router.post("/jobs/{job_id}/preview")
def preview(job_id: int, body: RunIn, user: User = Depends(need(*ANY_IMPORT)), db: Session = Depends(get_db)):
    """Dry run: the real code path, rolled back at the end, so nothing is saved."""
    rate_limit(f"smartimport-run:{user.id}", 60)
    job = _load(db, user, job_id)
    try:
        report, _ = _execute(db, user, job, body, commit=False)
    finally:
        db.rollback()
    return report


@router.post("/jobs/{job_id}/confirm")
def confirm(job_id: int, body: RunIn, user: User = Depends(need(*ANY_IMPORT)), db: Session = Depends(get_db)):
    rate_limit(f"smartimport-run:{user.id}", 60)
    job = _load(db, user, job_id)
    filename = job.filename
    try:
        report, ctx = _execute(db, user, job, body, commit=True)
        if not report["can_confirm"]:
            db.rollback()
            raise HTTPException(422, "The import has problems to fix first. Nothing was imported.")
        if not report["changes"]:
            db.rollback()
            return {**report, "imported": False, "batch_id": None, "logins": []}
        logins = []
        if ctx.pending:
            with ThreadPoolExecutor(max_workers=8) as ex:  # bcrypt releases the GIL
                hashes = list(ex.map(lambda t: hash_password(t[1], BULK_BCRYPT_ROUNDS), ctx.pending))
            for (u, pw, info), h in zip(ctx.pending, hashes):
                u.password_hash = h
                db.add(u)
                logins.append({**info, "temp_password": pw})
        db.flush()
        created = {k: [o.id for o in v] for k, v in ctx.new.items() if v}
        created["_updated"] = {t: d for t, d in ctx.updated.items() if d}
        summary = [{k: r[k] for k in ("label", "name", "rows", "new", "matched", "updated", "skipped")} for r in report["sheets"]]
        batch = ImportBatch(school_id=user.school_id, user_name=user.username, filename=filename, summary=summary, created=created)
        db.add(batch)
        db.execute(delete(ImportJob).where(ImportJob.id == job.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        log.warning("import_conflict")
        raise HTTPException(409, "Could not save because something changed while importing (for example another import ran). Nothing was imported; try again.")
    except Exception:
        db.rollback()
        raise
    return {**report, "imported": True, "batch_id": batch.id, "logins": logins}


def _iso(d: datetime) -> str:
    return d.isoformat() + "Z"


@router.get("/batches")
def batches(user: User = Depends(need(*ANY_IMPORT)), db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportBatch).where(ImportBatch.school_id == user.school_id).order_by(ImportBatch.id.desc()).limit(50))
    cutoff = _now() - timedelta(days=UNDO_DAYS)
    return [{"id": b.id, "filename": b.filename, "by": b.user_name, "at": _iso(b.created_at), "summary": b.summary,
             "counts": {k: len(v) for k, v in b.created.items() if k != "_updated" and v}, "undone": b.undone,
             "can_undo": not b.undone and b.created_at >= cutoff} for b in rows]


def _chunks(ids: list, n: int = 500):
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


@router.post("/batches/{batch_id}/undo")
def undo(batch_id: int, user: User = Depends(need(*ANY_IMPORT)), db: Session = Depends(get_db)):
    """Removes what this import created and puts back values it changed (only if they were not edited since)."""
    rate_limit(f"smartimport-undo:{user.id}", 20)
    b = db.get(ImportBatch, batch_id)
    if not b or b.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    if b.undone:
        raise HTTPException(409, "This import was already undone")
    if b.created_at < _now() - timedelta(days=UNDO_DAYS):
        raise HTTPException(409, f"Imports can only be undone within {UNDO_DAYS} days")
    perms = perm_set(user)
    touched = {CREATED_PERM[k] for k, v in b.created.items() if k in CREATED_PERM and v} | \
              {CREATED_PERM[k] for k in b.created.get("_updated", {})}
    if not touched <= perms:
        raise HTTPException(403, "You do not have permission to undo everything this import created")
    sid = user.school_id
    mine = select(Student.id).where(Student.school_id == sid)
    removed: dict = {}
    try:
        for table, model in (("payments", Payment), ("marks", Mark), ("fees", Fee)):
            ids = b.created.get(table, [])
            n = 0
            for part in _chunks(ids):
                n += db.execute(delete(model).where(model.id.in_(part), model.student_id.in_(mine))).rowcount
            if n:
                removed[table] = n
        upd = b.created.get("_updated", {})
        reverted = 0
        for table, model, col in (("marks", Mark, "score"), ("fees", Fee, "total_amount")):
            for oid, cols in upd.get(table, {}).items():
                row = db.scalar(select(model).join(Student, Student.id == model.student_id)
                                .where(model.id == int(oid), Student.school_id == sid))
                if row is not None and getattr(row, col) == cols[col][1]:
                    setattr(row, col, cols[col][0])
                    reverted += 1
        for oid, cols in upd.get("students", {}).items():
            row = db.scalar(select(Student).where(Student.id == int(oid), Student.school_id == sid))
            if row is not None and row.legacy_id == cols["legacy_id"][1]:
                row.legacy_id = cols["legacy_id"][0]
        if reverted:
            removed["values restored"] = reverted
        n = 0
        for part in _chunks(b.created.get("students", [])):
            for s in db.scalars(select(Student).where(Student.id.in_(part), Student.school_id == sid)):
                storage.remove(s.photo)
                storage.remove(s.pending_photo)
                db.delete(s)  # the database removes their login, any marks, fees, payments and attendance
                n += 1
        if n:
            removed["students"] = n
        n = 0
        for part in _chunks(b.created.get("staff", [])):
            for s in db.scalars(select(Staff).where(Staff.id.in_(part), Staff.school_id == sid)):
                for u in db.scalars(select(User).where(User.staff_id == s.id, User.school_id == sid, User.role == "staff")):
                    db.delete(u)
                storage.remove(s.photo)
                db.delete(s)
                n += 1
        if n:
            removed["staff"] = n
        db.flush()
        n = kept = 0
        for part in _chunks(b.created.get("subjects", [])):
            for sub in db.scalars(select(Subject).where(Subject.id.in_(part), Subject.school_id == sid)):
                in_use = db.scalar(select(func.count()).select_from(Mark).where(Mark.subject_id == sub.id)) or \
                    db.scalar(select(func.count()).select_from(Chapter).where(Chapter.subject_id == sub.id))
                if in_use:
                    kept += 1  # it has marks or chapters that are not from this import
                else:
                    db.delete(sub)
                    n += 1
        if n:
            removed["subjects"] = n
        for table, model in (("events", Event), ("goals", Goal)):
            n = 0
            for part in _chunks(b.created.get(table, [])):
                n += db.execute(delete(model).where(model.id.in_(part), model.school_id == sid)).rowcount
            if n:
                removed[table] = n
        b.undone = True
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"undone": True, "removed": removed, "subjects_kept": kept}
