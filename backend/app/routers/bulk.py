"""Bulk actions: import students from a CSV/Excel sheet, start a new academic year (promote classes), set fees for a class."""
import csv
import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import analytics
from ..db import get_db
from ..deps import next_code, year_of
from ..models import GRADES, Fee, School, Student, User
from ..routers.people import _check_limit
from ..schemas import YEAR, StudentIn
from ..security import gen_password, hash_password, need, perm_set, rate_limit

router = APIRouter(prefix="/api")

MAX_FILE = 2 * 1024 * 1024
MAX_ROWS = 300
MAX_UNZIPPED = 25 * 1024 * 1024
BULK_BCRYPT_ROUNDS = 10  # one-time random passwords, forced change at first login; keeps a 300-row import to a few seconds

ALIASES = {
    "name": ("name", "student_name", "full_name", "student"),
    "gender": ("gender", "sex"),
    "dob": ("dob", "date_of_birth", "birth_date", "birthdate"),
    "grade": ("class", "grade", "std", "standard"),
    "section": ("section", "sec"),
    "guardian_name": ("guardian_name", "guardian", "parent_name", "parent", "father_name", "mother_name"),
    "phone": ("phone", "mobile", "phone_number", "contact", "guardian_phone"),
    "email": ("email", "email_id", "guardian_email"),
    "blood_group": ("blood_group", "blood", "bloodgroup"),
    "address": ("address",),
}
REQUIRED = ("name", "gender", "dob", "grade", "section", "guardian_name", "phone")
TEMPLATE_HEADER = ["name", "gender", "dob", "class", "section", "guardian_name", "phone", "email", "blood_group", "address"]


# ---------- reading the sheet ----------
async def _read_body(request: Request) -> bytes:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_FILE:
        raise HTTPException(413, "File too large (max 2 MB)")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_FILE:
            raise HTTPException(413, "File too large (max 2 MB)")
    if not buf:
        raise HTTPException(422, "The file is empty")
    return bytes(buf)


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _table(data: bytes) -> list[list[str]]:
    if data[:4] == b"PK\x03\x04":  # .xlsx
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                    raise HTTPException(413, "The spreadsheet is too large when unpacked")
            from python_calamine import CalamineWorkbook
            wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
            rows = wb.get_sheet_by_index(0).to_python()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, "Could not read that Excel file. Save it as .xlsx or CSV and try again")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(422, "The CSV must be saved as UTF-8")
        try:
            dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    return [[_cell(c) for c in r] for r in rows if any(_cell(c) for c in r)]


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


def _columns(header: list[str]) -> dict[str, int]:
    idx = {}
    for i, h in enumerate(header):
        n = _norm_header(h)
        for field, names in ALIASES.items():
            if n in names and field not in idx:
                idx[field] = i
    missing = [f for f in REQUIRED if f not in idx]
    if missing:
        label = {"grade": "class", "guardian_name": "guardian_name"}
        raise HTTPException(422, "Missing column(s): " + ", ".join(label.get(m, m) for m in missing)
                            + ". Download the template to see the expected headings.")
    return idx


# ---------- cleaning one row ----------
def _grade(v: str) -> str:
    s = re.sub(r"\b(class|standard|std)\b\.?", "", v.strip().lower()).strip().replace(".", "")
    s = re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", s)
    return s.upper() if s in ("lkg", "ukg") else s


def _gender(v: str) -> str:
    s = v.strip().lower()
    return {"m": "Male", "male": "Male", "boy": "Male", "f": "Female", "female": "Female", "girl": "Female"}.get(s, "Other" if s == "other" else v)


def _dob(v: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    return v  # StudentIn will reject it with a clear message


def _clean(raw: dict) -> dict:
    out = {k: (raw.get(k) or "").strip() for k in ALIASES}
    out["grade"], out["gender"], out["dob"] = _grade(out["grade"]), _gender(out["gender"]), _dob(out["dob"])
    out["section"] = out["section"].upper()[:1] if out["section"] else out["section"]
    out["blood_group"] = (out["blood_group"].upper().replace(" ", "") or None)
    for k in ("email", "address"):
        out[k] = out[k] or None
    return out


def _parse(data: bytes, db: Session, school_id: int) -> tuple[list[StudentIn], list[dict]]:
    table = _table(data)
    if len(table) < 2:
        raise HTTPException(422, "The file has no student rows")
    cols = _columns(table[0])
    body = table[1:]
    if len(body) > MAX_ROWS:
        raise HTTPException(422, f"At most {MAX_ROWS} students per file. Split the file and import in parts.")
    seen = {(n.lower(), d, g) for n, d, g in db.execute(
        select(Student.name, Student.dob, Student.grade).where(Student.school_id == school_id))}
    good, errors = [], []
    for n, row in enumerate(body, start=2):  # row 1 is the header, like the sheet
        raw = {f: (row[i] if i < len(row) else "") for f, i in cols.items()}
        try:
            s = StudentIn(**_clean(raw))
        except ValidationError as e:
            msg = "; ".join(f"{(x['loc'][-1] if x['loc'] else 'row')}: {x['msg'].removeprefix('Value error, ')}" for x in e.errors())
            errors.append({"row": n, "name": raw.get("name") or "", "message": msg})
            continue
        key = (s.name.lower(), s.dob, s.grade)
        if key in seen:
            errors.append({"row": n, "name": s.name, "message": "already exists (same name, date of birth and class)"})
            continue
        seen.add(key)
        good.append(s)
    return good, errors


@router.get("/students/import/template")
def template(_: User = Depends(need("students.manage"))):
    from ..reports import download
    sample = ["Asha Rao", "Female", "2014-06-21", "5", "A", "Ravi Rao", "9876543210", "asha.parent@example.com", "O+", "12 Main Road"]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(TEMPLATE_HEADER)
    w.writerow(sample)
    return download(out.getvalue().encode(), "students-template.csv", "text/csv; charset=utf-8")


@router.post("/students/import")
async def import_students(request: Request, dry_run: bool = Query(True),
                          user: User = Depends(need("students.manage")), db: Session = Depends(get_db)):
    rate_limit(f"import:{user.id}", 20)
    data = await _read_body(request)
    return _import(db, user, data, dry_run)


def _import(db: Session, user: User, data: bytes, dry_run: bool) -> dict:
    good, errors = _parse(data, db, user.school_id)
    summary = {"rows": len(good) + len(errors), "valid": len(good), "errors": errors,
               "preview": [{"name": s.name, "class": f"{s.grade}-{s.section}", "guardian": s.guardian_name} for s in good[:8]]}
    if dry_run:
        return {**summary, "imported": 0}
    if errors:
        raise HTTPException(422, f"{len(errors)} row(s) need fixing. Nothing was imported.")
    if not good:
        raise HTTPException(422, "There are no students to import")
    school = db.get(School, user.school_id)
    have = db.scalar(select(func.count()).select_from(Student).where(Student.school_id == user.school_id))
    if have + len(good) > school.max_students:
        raise HTTPException(403, f"Your plan allows at most {school.max_students} student records "
                                 f"({have} now, {len(good)} in this file). Contact the platform team to raise it.")
    passwords = [gen_password() for _ in good]
    with ThreadPoolExecutor(max_workers=8) as ex:  # bcrypt releases the GIL, so this runs in parallel
        hashes = list(ex.map(lambda p: hash_password(p, BULK_BCRYPT_ROUNDS), passwords))
    logins = []
    try:
        for s, pw, h in zip(good, passwords, hashes):
            code = next_code(db, user.school_id, "s", s.grade)
            st = Student(school_id=user.school_id, admission_no=code, **s.model_dump(exclude={"admission_no"}))
            db.add(st)
            db.flush()
            db.add(User(school_id=user.school_id, username=code, password_hash=h, role="student",
                        full_name=st.name, student_id=st.id, must_change=True))
            logins.append({"student_id": code, "name": st.name, "class": f"{st.grade}-{st.section}", "temp_password": pw})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Could not allocate student IDs (another import may be running). Nothing was imported; try again.")
    return {**summary, "imported": len(logins), "logins": logins}


# ---------- new academic year ----------
def next_year(y: str) -> str:
    a = int(y[:4]) + 1
    return f"{a}-{str(a + 1)[2:]}"


def _next_grade(g: str) -> Optional[str]:
    i = GRADES.index(g)
    return GRADES[i + 1] if i + 1 < len(GRADES) else None


@router.get("/school/new-year")
def new_year_preview(user: User = Depends(need("school.manage")), db: Session = Depends(get_db)):
    cur = year_of(db, user.school_id)
    overall = analytics.student_overall_map(db, user.school_id, cur)
    by: dict[str, list] = {g: [] for g in GRADES}
    for s in db.scalars(select(Student).where(Student.school_id == user.school_id).order_by(Student.section, Student.name)):
        by[s.grade].append({"id": s.id, "name": s.name, "section": s.section, "admission_no": s.admission_no,
                            "overall_pct": overall.get(s.id)})
    return {"current_year": cur, "next_year": next_year(cur), "pass_mark": analytics.WEAK_BELOW,
            "grades": [{"grade": g, "next": _next_grade(g), "students": by[g]} for g in GRADES]}


class NewYearIn(BaseModel):
    year: str = Field(pattern=YEAR)  # must be the year after the current one: stops a repeated click promoting twice
    hold_back: list[int] = Field(default=[], max_length=2000)
    remove_graduates: bool = False


@router.post("/school/new-year")
def start_new_year(data: NewYearIn, user: User = Depends(need("school.manage")), db: Session = Depends(get_db)):
    if "students.manage" not in perm_set(user):  # it moves students, so both permissions are needed
        raise HTTPException(403, "You do not have permission to do this")
    school = db.get(School, user.school_id)
    cur = year_of(db, user.school_id)
    if data.year != next_year(cur):
        raise HTTPException(409, f"The current year is {cur}. The next year is {next_year(cur)}. "
                                 "If you already started it, nothing more is needed.")
    held = set(data.hold_back)
    studs = list(db.scalars(select(Student).where(Student.school_id == user.school_id)))
    unknown = held - {s.id for s in studs}
    if unknown:
        raise HTTPException(422, "Some held-back students are not in this school")
    moved = kept = graduated = removed = 0
    for s in studs:
        nxt = _next_grade(s.grade)
        if s.id in held:
            kept += 1
        elif nxt is None:
            if data.remove_graduates:
                db.delete(s)
                removed += 1
            else:
                graduated += 1
        else:
            s.grade = nxt  # every grade changes by exactly one step, so processing order does not matter
            moved += 1
    school.academic_year = data.year
    db.commit()
    return {"year": data.year, "promoted": moved, "held_back": kept, "class10_remaining": graduated, "class10_removed": removed}


# ---------- fees for a whole class ----------
class BulkFeeIn(BaseModel):
    year: str = Field(pattern=YEAR)
    grade: str
    total_amount: float = Field(ge=0, le=10_000_000)


@router.put("/fees/bulk")
def set_class_fee(data: BulkFeeIn, user: User = Depends(need("fees.manage")), db: Session = Depends(get_db)):
    if data.grade not in GRADES:
        raise HTTPException(422, "Unknown class")
    ids = list(db.scalars(select(Student.id).where(Student.school_id == user.school_id, Student.grade == data.grade)))
    have = {f.student_id: f for f in db.scalars(select(Fee).where(Fee.academic_year == data.year, Fee.student_id.in_(ids or [0])))}
    for sid in ids:
        if sid in have:
            have[sid].total_amount = data.total_amount
        else:
            db.add(Fee(student_id=sid, academic_year=data.year, total_amount=data.total_amount))
    db.commit()
    return {"students": len(ids)}
