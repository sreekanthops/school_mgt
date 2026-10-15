"""Smart import, part 1: read an xlsx / csv / json / docx file, work out what each sheet holds and which column is which.
Nothing here touches the database. Only column headings (never student rows) are ever sent to an optional AI service."""
import csv
import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import httpx
from xml.etree import ElementTree as ET  # DOCTYPE / ENTITY declarations are refused before parsing (see _read_docx)

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

log = logging.getLogger("school.import")

MAX_FILE = 5 * 1024 * 1024
MAX_UNZIPPED = 25 * 1024 * 1024
MAX_SHEETS = 25
MAX_COLS = 80
MAX_ROWS_SHEET = 5000
MAX_ROWS_TOTAL = 20000
MAX_CELL = 500


class ImportFileError(ValueError):
    """A problem with the uploaded file that the user can fix. The message is safe to show."""


# ---------- what we know how to import ----------
# kind -> {"label", "perm", "fields": {field: (label, required, aliases)}}
KINDS: dict = {
    "students": {"label": "Students", "perm": "students.manage", "fields": {
        "name": ("Name", True, ("name", "student_name", "full_name", "student", "pupil", "pupil_name", "name_of_student")),
        "gender": ("Gender", True, ("gender", "sex")),
        "dob": ("Date of birth", True, ("dob", "date_of_birth", "birth_date", "birthdate", "d_o_b")),
        "grade": ("Class", True, ("class", "grade", "std", "standard", "class_name", "class_studying")),
        "section": ("Section", False, ("section", "sec", "division", "div")),
        "guardian_name": ("Guardian name", True, ("guardian_name", "guardian", "parent_name", "parent", "father_name",
                                                  "mother_name", "father", "mother", "parent_guardian")),
        "phone": ("Phone", True, ("phone", "mobile", "phone_number", "contact", "contact_no", "mobile_no", "guardian_phone",
                                  "parent_phone", "phone_no")),
        "email": ("Email", False, ("email", "email_id", "guardian_email", "parent_email")),
        "blood_group": ("Blood group", False, ("blood_group", "blood", "bloodgroup")),
        "address": ("Address", False, ("address",)),
        "legacy_id": ("Old ID / admission no.", False, ("legacy_id", "old_id", "admission_no", "admission_number", "adm_no",
                                                        "reg_no", "registration_no", "student_id", "id", "sr_no", "scholar_no")),
    }},
    "staff": {"label": "Staff", "perm": "staff.manage", "fields": {
        "name": ("Name", True, ("name", "staff_name", "employee_name", "teacher_name", "full_name", "teacher")),
        "gender": ("Gender", True, ("gender", "sex")),
        "designation": ("Role / designation", True, ("designation", "role", "position", "post", "title", "job_title")),
        "department": ("Department", False, ("department", "dept")),
        "qualification": ("Qualification", False, ("qualification", "education", "degree")),
        "experience_years": ("Experience (years)", False, ("experience", "exp", "years_of_experience", "experience_years")),
        "subjects": ("Subjects taught", False, ("subject", "subjects", "subject_taught", "teaches")),
        "class_teacher_of": ("Class teacher of", False, ("class_teacher", "class_teacher_of", "class_in_charge")),
        "phone": ("Phone", True, ("phone", "mobile", "phone_number", "contact", "contact_no", "mobile_no", "phone_no")),
        "email": ("Email", True, ("email", "email_id")),
        "joined_on": ("Joining date", False, ("joined", "joining_date", "date_of_joining", "doj", "joined_on", "join_date")),
        "bio": ("About", False, ("bio", "about", "notes")),
        "legacy_id": ("Old ID / employee no.", False, ("legacy_id", "employee_id", "emp_id", "emp_no", "staff_id", "id",
                                                       "employee_no", "employee_code")),
    }},
    "subjects": {"label": "Subjects", "perm": "subjects.manage", "fields": {
        "name": ("Subject", True, ("subject", "subject_name", "name")),
        "grade": ("Class", True, ("class", "grade", "std", "standard")),
    }},
    "marks": {"label": "Marks", "perm": "marks.edit", "fields": {
        "student_id": ("Student ID / admission no.", False, ("student_id", "admission_no", "admission_number", "adm_no", "id",
                                                             "legacy_id", "reg_no", "registration_no", "old_id")),
        "name": ("Student name", False, ("student_name", "name", "student", "pupil", "pupil_name", "full_name")),
        "grade": ("Class", False, ("class", "grade", "std", "standard")),
        "section": ("Section", False, ("section", "sec", "division")),
        "subject": ("Subject", False, ("subject", "subject_name", "course")),
        "exam": ("Exam / test", False, ("exam", "test", "exam_name", "test_name", "assessment", "term", "exam_type")),
        "year": ("Academic year", False, ("year", "academic_year", "session", "ay")),
        "score": ("Marks obtained", False, ("score", "marks", "marks_obtained", "obtained", "mark", "secured", "scored")),
        "max": ("Maximum marks", False, ("max", "max_marks", "out_of", "total_marks", "maximum", "max_score", "full_marks")),
    }},
    "fees": {"label": "Fees", "perm": "fees.manage", "fields": {
        "student_id": ("Student ID / admission no.", False, ("student_id", "admission_no", "admission_number", "adm_no", "id",
                                                             "legacy_id", "reg_no", "old_id")),
        "name": ("Student name", False, ("student_name", "name", "student", "pupil", "full_name")),
        "grade": ("Class", False, ("class", "grade", "std", "standard")),
        "section": ("Section", False, ("section", "sec", "division")),
        "year": ("Academic year", False, ("year", "academic_year", "session", "ay")),
        "total_amount": ("Total fee", True, ("total", "total_fee", "total_fees", "fee", "fees", "fee_amount", "amount_due",
                                             "annual_fee", "total_amount", "fee_total")),
        "paid": ("Amount paid so far", False, ("paid", "amount_paid", "paid_amount", "received", "collected")),
        "paid_on": ("Paid on", False, ("paid_on", "payment_date", "date_paid", "paid_date", "date")),
        "mode": ("Payment mode", False, ("payment_mode", "mode")),
    }},
    "payments": {"label": "Fee payments", "perm": "fees.manage", "fields": {
        "student_id": ("Student ID / admission no.", False, ("student_id", "admission_no", "admission_number", "adm_no", "id",
                                                             "legacy_id", "reg_no", "old_id")),
        "name": ("Student name", False, ("student_name", "name", "student", "pupil", "full_name")),
        "grade": ("Class", False, ("class", "grade", "std", "standard")),
        "section": ("Section", False, ("section", "sec", "division")),
        "year": ("Academic year", False, ("year", "academic_year", "session", "ay")),
        "amount": ("Amount paid", True, ("amount", "amount_paid", "paid_amount", "payment", "payment_amount", "receipt_amount")),
        "paid_on": ("Paid on", False, ("paid_on", "payment_date", "date_paid", "paid_date", "date")),
        "mode": ("Payment mode", False, ("payment_mode", "mode")),
    }},
    "events": {"label": "Events", "perm": "content.manage", "fields": {
        "title": ("Title", True, ("title", "event", "event_name", "name")),
        "date": ("Date", True, ("date", "event_date", "on")),
        "location": ("Location", False, ("location", "venue", "place")),
        "category": ("Category", False, ("category", "type", "event_type")),
        "description": ("Description", False, ("description", "details", "about")),
    }},
    "goals": {"label": "Goals", "perm": "content.manage", "fields": {
        "title": ("Goal", True, ("goal", "title", "objective")),
        "description": ("Description", False, ("description", "details")),
        "target_year": ("Target year", True, ("target_year", "year", "by", "target")),
        "progress": ("Progress %", False, ("progress", "percent_complete", "progress_percent")),
        "status": ("Status", False, ("status",)),
    }},
}
KIND_ORDER = ["subjects", "students", "staff", "fees", "payments", "marks", "events", "goals"]
# a sheet is only taken as this kind if at least one of these columns is present
DISTINCT = {"students": {"dob", "guardian_name"}, "staff": {"designation", "joined_on"}, "marks": {"subject", "score"},
            "fees": {"total_amount"}, "payments": {"amount"}, "events": {"date", "location"},
            "goals": {"target_year", "progress"}, "subjects": set()}
NAME_HINTS = {"students": ("student", "pupil"), "staff": ("staff", "teacher", "faculty", "employee"),
              "subjects": ("subject",), "marks": ("mark", "result", "score"), "fees": ("fee",),
              "payments": ("payment", "receipt"), "events": ("event",), "goals": ("goal",)}


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


# ---------- reading files ----------
@dataclass
class Sheet:
    name: str
    rows: list  # list[list[str]], blank trailing rows removed, original row positions kept


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v)).strip()[:MAX_CELL]


def _sheet(name: str, rows) -> Sheet:
    out = [[_cell(c) for c in r][:MAX_COLS] for r in rows]
    while out and not any(out[-1]):
        out.pop()
    return Sheet(re.sub(r"[\x00-\x1f]", "", name)[:60] or "Sheet", out)


def _check_zip(z: zipfile.ZipFile) -> None:
    infos = z.infolist()
    if len(infos) > 3000 or sum(i.file_size for i in infos) > MAX_UNZIPPED:
        raise ImportFileError("The file is too large when unpacked")
    if any(i.filename.lower().endswith("vbaproject.bin") for i in infos):
        raise ImportFileError("Files with macros are not accepted. Save a copy without macros and try again")


def _read_xlsx(data: bytes) -> list[Sheet]:
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    return [_sheet(n, wb.get_sheet_by_name(n).to_python()) for n in wb.sheet_names[:MAX_SHEETS]]


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _read_docx(z: zipfile.ZipFile) -> list[Sheet]:
    xml = z.read("word/document.xml")
    try:
        text = xml.decode("utf-8")  # strict UTF-8 only, so the marker check below cannot be dodged by another encoding
    except UnicodeDecodeError:
        raise ImportFileError("That Word file contains unsupported content")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():  # no entity tricks (XXE / entity expansion)
        raise ImportFileError("That Word file contains unsupported content")
    root = ET.fromstring(xml)
    sheets = []
    for t in root.iter(W + "tbl"):
        rows = []
        for tr in t.findall(W + "tr"):
            rows.append([" ".join("".join(x.text or "" for x in p.iter(W + "t")) for p in tc.findall(W + "p")).strip()
                         for tc in tr.findall(W + "tc")])
        if len(rows) >= 2:
            sheets.append(_sheet(f"Table {len(sheets) + 1}", rows))
        if len(sheets) >= MAX_SHEETS:
            break
    if not sheets:
        raise ImportFileError("No tables were found in that Word file. Put the data in a table (one row per record, with a heading row)")
    return sheets


def _read_csv(text: str) -> list[Sheet]:
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [_sheet("Sheet1", csv.reader(io.StringIO(text), dialect))]


def _scalar(v) -> str:
    if isinstance(v, list):
        return ", ".join(_cell(x) if not isinstance(x, (dict, list)) else json.dumps(x)[:80] for x in v)
    if isinstance(v, dict):
        return json.dumps(v)[:MAX_CELL]
    return _cell(v)


def _json_sheets(name: str, node, out: list, depth: int = 0) -> None:
    """Flexible shapes: a list of records, an object holding lists (one sheet per list), id -> record maps, and lists
    nested inside records (their rows carry the parent's simple fields, e.g. a student's marks)."""
    if len(out) >= MAX_SHEETS or depth > 4:
        return
    if isinstance(node, dict):
        vals = [v for v in node.values() if v not in (None, "", [], {})]
        if vals and all(isinstance(v, (list, dict)) for v in vals):  # a container of collections: one sheet each
            for k, v in node.items():
                if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
                    v = [{"id": kk, **x} for kk, x in v.items()]  # id -> record map
                if isinstance(v, (list, dict)):
                    _json_sheets(str(k), v, out, depth + 1)
            return
        node = [node]
    if not isinstance(node, list):
        return
    records = [r for r in node if isinstance(r, dict)]
    if not records:
        return
    main, children = [], {}
    for r in records:
        simple = {k: _scalar(v) for k, v in r.items() if not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v))}
        main.append(simple)
        for k, v in r.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                children.setdefault(k, []).extend({**simple, **{ck: _scalar(cv) for ck, cv in c.items()}} for c in v)
    for sheet_name, recs in [(name, main)] + [(f"{name}.{k}", v) for k, v in children.items()]:
        heads = list(dict.fromkeys(k for r in recs for k in r))[:MAX_COLS]
        out.append(_sheet(sheet_name, [heads] + [[r.get(h, "") for h in heads] for r in recs]))


def read_file(data: bytes) -> list[Sheet]:
    """Detects the type from the content, not the file name."""
    if not data:
        raise ImportFileError("The file is empty")
    if len(data) > MAX_FILE:
        raise ImportFileError("File too large (max 5 MB)")
    try:
        if data[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                _check_zip(z)
                names = set(z.namelist())
                if "word/document.xml" in names:
                    sheets = _read_docx(z)
                elif "xl/workbook.xml" in names:
                    sheets = None
                else:
                    raise ImportFileError("Unsupported file. Use .xlsx, .csv, .json or .docx")
            sheets = sheets if sheets is not None else _read_xlsx(data)
        elif data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise ImportFileError("Old Excel/Word formats (.xls/.doc) are not supported. Save as .xlsx or .docx and try again")
        elif data[:5] == b"%PDF-":
            raise ImportFileError("PDF files cannot be read reliably. Export the data as Excel or CSV instead")
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ImportFileError("Text files must be saved as UTF-8")
            if text.lstrip()[:1] in "{[":
                try:
                    node = json.loads(text)
                except ValueError:
                    raise ImportFileError("That JSON file is not valid")
                sheets: list = []
                _json_sheets("data", node, sheets)
            else:
                sheets = _read_csv(text)
    except ImportFileError:
        raise
    except Exception:  # noqa: BLE001 - corrupt or hostile file: one safe message
        log.warning("import_unreadable_file")
        raise ImportFileError("Could not read that file. Check it opens normally, then try again")
    sheets = [s for s in sheets if len(s.rows) >= 2]
    if not sheets:
        raise ImportFileError("The file has no data rows")
    if any(len(s.rows) > MAX_ROWS_SHEET + 10 for s in sheets):
        raise ImportFileError(f"A sheet has more than {MAX_ROWS_SHEET} rows. Split it into smaller files")
    if sum(len(s.rows) for s in sheets) > MAX_ROWS_TOTAL:
        raise ImportFileError(f"The file has more than {MAX_ROWS_TOTAL} rows in total. Split it into smaller files")
    return sheets


# ---------- working out what a sheet is ----------
def auto_map(kind: str, header: list[str]) -> dict[str, int]:
    heads = [norm_header(h) for h in header]
    used, out = set(), {}
    for field, (_, _, aliases) in KINDS[kind]["fields"].items():
        for i, h in enumerate(heads):
            if i not in used and h in aliases:
                out[field] = i
                used.add(i)
                break
    return out


def classify(sheet_name: str, header: list[str]) -> tuple[Optional[str], float, dict]:
    best, best_score, best_map = None, 0.0, {}
    n = sheet_name.lower()
    for kind in KIND_ORDER:
        m = auto_map(kind, header)
        score = float(len(m))
        if DISTINCT[kind] and not (set(m) & DISTINCT[kind]):
            score = 0.0
        if kind == "subjects" and len(header) > 3:
            score = 0.0  # a two-column list; a wider sheet is something else
        if score and any(h in n for h in NAME_HINTS[kind]):
            score += 1.5
        if score > best_score:
            best, best_score, best_map = kind, score, m
    return (best, best_score, best_map) if best_score >= 2 else (None, best_score, {})


def analyse(sheet: Sheet) -> dict:
    """Finds the heading row (titles above the table are skipped), the kind of data and a column mapping."""
    pick = None
    for i, row in enumerate(sheet.rows[:10]):
        if sum(1 for c in row if c) < 2:
            continue
        kind, score, m = classify(sheet.name, row)
        if pick is None or score > pick[1]:
            pick = (i, score, kind, m)
    h = pick[0] if pick else 0
    kind, m = (pick[2], pick[3]) if pick else (None, {})
    header = sheet.rows[h] if sheet.rows else []
    return {"header_row": h, "kind": kind, "mapping": m, "headers": header,
            "start": h + 1, "rows": sum(1 for r in sheet.rows[h + 1:] if any(r)),
            "sample": [r for r in sheet.rows[h + 1:h + 4]]}


# ---------- optional AI help: headings only ----------
def llm_enabled() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL) and LLM_BASE_URL.startswith("https://")


def llm_suggest(sheets: list[dict]) -> dict[int, dict]:
    """sheets: [{"index", "name", "headers"}] for the sheets the rules could not fully map. Only the sheet name and
    the column headings are sent: no cell values, so no student or staff data leaves the system. The answer is
    validated: only known kinds, known fields and headings that really exist are accepted. Returns {index: {"kind", "mapping"}}."""
    if not llm_enabled() or not sheets:
        return {}
    spec = {k: list(v["fields"]) for k, v in KINDS.items()}
    payload = [{"index": s["index"], "sheet": s["name"][:60], "columns": [h[:60] for h in s["headers"]][:MAX_COLS]} for s in sheets]
    try:
        r = httpx.post(
            LLM_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={"model": LLM_MODEL, "temperature": 0, "messages": [
                {"role": "system", "content": "You map spreadsheet column headings of a school's records to fields. "
                 "Reply with JSON only: {\"sheets\":[{\"index\":0,\"kind\":\"<kind or null>\",\"mapping\":{\"<field>\":\"<exact column heading>\"}}]}. "
                 "Use only the kinds and fields given, and only headings that appear in the list. Omit fields you are unsure about."},
                {"role": "user", "content": json.dumps({"kinds_and_fields": spec, "sheets": payload})}]},
            timeout=20.0,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = text[text.index("{"):text.rindex("}") + 1]
        answer = json.loads(text)["sheets"]
    except Exception:  # noqa: BLE001 - the rules still work without it
        log.warning("llm_import_unavailable")
        return {}
    by_index = {s["index"]: s for s in sheets}
    out = {}
    for a in answer if isinstance(answer, list) else []:
        s = by_index.get(a.get("index")) if isinstance(a, dict) else None
        kind = a.get("kind") if s else None
        if not s or kind not in KINDS or not isinstance(a.get("mapping"), dict):
            continue
        mapping = {}
        for field, head in a["mapping"].items():
            if field in KINDS[kind]["fields"] and isinstance(head, str) and head in s["headers"]:
                mapping[field] = s["headers"].index(head)
        out[s["index"]] = {"kind": kind, "mapping": mapping}
    return out


# ---------- value helpers shared with the importer ----------
EXAM_ALIASES = {
    "UT1": ("ut1", "ut_1", "unit_test_1", "unit_test1", "unit_test", "pt1", "pt_1", "periodic_test_1", "fa1", "fa_1", "test_1", "test1"),
    "Midterm": ("midterm", "mid_term", "mid", "half_yearly", "halfyearly", "term_1", "term1", "sa1", "sa_1", "quarterly"),
    "UT2": ("ut2", "ut_2", "unit_test_2", "unit_test2", "pt2", "pt_2", "periodic_test_2", "fa2", "fa_2", "test_2", "test2"),
    "Final": ("final", "final_exam", "annual", "annual_exam", "yearly", "term_2", "term2", "sa2", "sa_2"),
}
_EXAM_LOOKUP = {a: e for e, al in EXAM_ALIASES.items() for a in al}


def norm_exam(v: str) -> Optional[str]:
    return _EXAM_LOOKUP.get(norm_header(v))


def norm_year(v: str) -> Optional[str]:
    m = re.fullmatch(r"\s*(\d{4})\s*[-/\u2013]\s*(\d{2}|\d{4})\s*", v or "")
    if not m:
        return None
    a, b = int(m[1]), int(m[2][-2:])
    return f"{a}-{b:02d}" if b == (a + 1) % 100 else None


def parse_date(v: str) -> Optional[date]:
    v = (v or "").strip()[:10] if re.match(r"\d{4}-\d{2}-\d{2}", v or "") else (v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


SYNONYMS = {
    "maths": "mathematics", "math": "mathematics", "mathematics": "mathematics",
    "sci": "science", "general science": "science", "eng": "english", "social": "social studies",
    "social science": "social studies", "sst": "social studies", "computer": "computer science",
    "computers": "computer science", "comp science": "computer science", "cs": "computer science", "pe": "physical education",
    "phys ed": "physical education", "pt": "physical education", "environmental studies": "evs", "env studies": "evs",
    "art and craft": "art craft", "hindi": "hindi", "telugu": "telugu",
}


def canon_subject(name: str) -> str:
    n = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return SYNONYMS.get(n, n)


def norm_name(v: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", v.lower()).split())


PAY_MODES = {"cash": "Cash", "upi": "UPI", "gpay": "UPI", "phonepe": "UPI", "paytm": "UPI", "card": "Card", "credit card": "Card",
             "debit card": "Card", "cheque": "Cheque", "check": "Cheque", "dd": "Cheque", "bank transfer": "Bank Transfer",
             "bank": "Bank Transfer", "neft": "Bank Transfer", "imps": "Bank Transfer", "rtgs": "Bank Transfer",
             "online": "Bank Transfer", "net banking": "Bank Transfer", "netbanking": "Bank Transfer"}
