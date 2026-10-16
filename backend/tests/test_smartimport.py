"""Smart import: parsing, classification, matching, idempotence, undo, safety."""
import io
import json
import zipfile

import openpyxl
from sqlalchemy import func, select

from app import smartimport as si
from app.db import SessionLocal
from app.models import Fee, ImportBatch, Mark, Payment, School, Staff, Student, Subject, User
from .conftest import login

STU = ["name", "gender", "dob", "class", "section", "guardian_name", "phone", "admission_no"]


def xlsx(sheets: dict) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def docx(rows, extra="") -> bytes:
    trs = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r) + "</w:tr>" for r in rows)
    body = f'<?xml version="1.0"?>{extra}<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>{trs}</w:tbl></w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", body)
    return out.getvalue()


def up(client, h, data, name="school.xlsx"):
    return client.post(f"/api/import/upload?filename={name}", headers=h, content=data)


def cfgs(up_json, **over):
    out = []
    for a in up_json["sheets"]:
        if a["kind"]:
            out.append({"index": a["index"], "kind": a["kind"], "header_row": a["header_row"], "mapping": a["mapping"], **over})
    return out


def run(client, h, job, body, path="preview"):
    return client.post(f"/api/import/jobs/{job}/{path}", headers=h, json=body)


def counts():
    with SessionLocal() as db:
        return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in (Student, Staff, Mark, Fee, Payment, Subject, User)}


SCHOOL_FILE = {
    "Students": [STU,
                 ["Ravi Kumar", "M", "12/03/2013", "6", "A", "Suresh Kumar", "9000000001", "OLD-1"],
                 ["Priya Nair", "F", "2013-05-04", "Class 6", "B", "Anil Nair", "9000000002", "OLD-2"]],
    "Subjects": [["Subject", "Class"], ["Maths", "6"], ["English", "6"]],
    "Marks": [["Admission No", "Subject", "Exam", "Marks", "Out of"],
              ["OLD-1", "Maths", "Unit Test 1", 20, 25], ["OLD-1", "English", "UT1", 18, 25], ["OLD-2", "Maths", "UT1", 10, 25]],
    "Fees": [["Student", "Class", "Total Fee", "Paid"], ["Ravi Kumar", "6A", "30,000", "10,000"], ["Priya Nair", "6B", "30000", 0]],
}


# ---------- parsing and classification (no database) ----------
def test_classifies_each_sheet_and_maps_columns():
    sheets = si.read_file(xlsx(SCHOOL_FILE))
    kinds = {s.name: si.analyse(s)["kind"] for s in sheets}
    assert kinds == {"Students": "students", "Subjects": "subjects", "Marks": "marks", "Fees": "fees"}
    a = si.analyse(sheets[0])
    assert a["mapping"]["legacy_id"] == 7 and a["mapping"]["grade"] == 3


def test_title_rows_above_the_table_are_skipped():
    rows = [["Greenfield School - student list"], [], STU, ["Ravi Kumar", "M", "12/03/2013", "6", "A", "Suresh", "9000000001", "1"]]
    a = si.analyse(si.read_file(xlsx({"Sheet1": rows}))[0])
    assert a["kind"] == "students" and a["header_row"] == 2


def test_json_shapes():
    nested = {"students": [{"name": "A B", "dob": "2014-01-01", "guardian": "X", "marks": [{"subject": "Maths", "exam": "UT1", "score": 5}]}]}
    got = {s.name: si.analyse(s)["kind"] for s in si.read_file(json.dumps(nested).encode())}
    assert got == {"students": "students", "students.marks": "marks"}
    plain = si.read_file(json.dumps([{"name": "T", "designation": "Teacher", "email": "a@b.co", "joined": "2020-01-01"}]).encode())
    assert si.analyse(plain[0])["kind"] == "staff"


def test_docx_tables_and_csv():
    d = si.read_file(docx([["Subject", "Class"], ["Maths", "7"]]))
    assert si.analyse(d[0])["kind"] == "subjects"
    c = si.read_file(b"Subject;Class\nMaths;7\n")
    assert si.analyse(c[0])["kind"] == "subjects"


def test_hostile_files_are_rejected():
    for bad in (b"", b"%PDF-1.4 x", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1xx", b"{not json", b"PK\x03\x04garbage"):
        try:
            si.read_file(bad)
        except si.ImportFileError:
            continue
        raise AssertionError(f"accepted {bad[:10]!r}")
    evil = docx([["a", "b"], ["1", "2"]], extra='<!DOCTYPE x [<!ENTITY e "boom">]>')
    try:
        si.read_file(evil)
        raise AssertionError("DOCTYPE accepted")
    except si.ImportFileError:
        pass
    macro = io.BytesIO()
    with zipfile.ZipFile(macro, "w") as z:
        z.writestr("xl/workbook.xml", "x")
        z.writestr("xl/vbaProject.bin", "x")
    try:
        si.read_file(macro.getvalue())
        raise AssertionError("macro file accepted")
    except si.ImportFileError:
        pass


def test_oversized_inputs_are_refused():
    try:
        si.read_file(b"a,b\n" + b"1,2\n" * (si.MAX_FILE // 4 + 10))
        raise AssertionError("too big accepted")
    except si.ImportFileError:
        pass


def test_value_helpers():
    assert si.norm_year("2025/26") == "2025-26" and si.norm_year("2025-2026") == "2025-26" and si.norm_year("2025-30") is None
    assert si.norm_exam("Unit Test 1") == "UT1" and si.norm_exam("Half Yearly") == "Midterm" and si.norm_exam("Quiz") is None
    assert si.canon_subject("Maths") == si.canon_subject("Mathematics")
    assert str(si.parse_date("12/03/2013")) == "2013-03-12" and si.parse_date("bad") is None


class FakeResp:
    def __init__(self, content): self._c = content
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": self._c}}]}


def test_llm_receives_only_headings_and_its_answer_is_validated(monkeypatch):
    sent = []
    monkeypatch.setattr(si, "LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setattr(si, "LLM_API_KEY", "k")
    monkeypatch.setattr(si, "LLM_MODEL", "m")
    reply = json.dumps({"sheets": [{"index": 0, "kind": "students",
                                    "mapping": {"name": "Pupil Full", "dob": "Nope", "evil": "Pupil Full", "phone": "Mob"}}]})
    monkeypatch.setattr(si.httpx, "post", lambda url, **kw: (sent.append(kw["json"]), FakeResp(reply))[1])
    out = si.llm_suggest([{"index": 0, "name": "X", "headers": ["Pupil Full", "Mob"]}])
    assert out == {0: {"kind": "students", "mapping": {"name": 0, "phone": 1}}}  # unknown field / heading dropped
    blob = json.dumps(sent)
    assert "Pupil Full" in blob and "9000000001" not in blob
    monkeypatch.setattr(si, "LLM_BASE_URL", "http://plain.example")
    assert si.llm_suggest([{"index": 0, "name": "X", "headers": ["a"]}]) == {}   # https only


# ---------- the whole flow ----------
def test_full_import_then_idempotent_then_undo(client, world):
    h = login(client, "ownerA")
    before = counts()
    j = up(client, h, xlsx(SCHOOL_FILE)).json()
    assert [a["kind"] for a in j["sheets"]] == ["students", "subjects", "marks", "fees"]
    body = {"sheets": cfgs(j, year="2025-26")}
    r = run(client, h, j["job_id"], body).json()
    assert r["errors"] == 0 and r["can_confirm"], r
    assert r["totals"] == {"students": 2, "subjects": 2, "marks": 3, "fees": 2, "payments": 1}
    assert counts() == before                                       # a dry run writes nothing
    done = run(client, h, j["job_id"], body, "confirm").json()
    assert done["imported"] and len(done["logins"]) == 2 and all(l["temp_password"] for l in done["logins"])
    after = counts()
    assert after["Student"] == before["Student"] + 2 and after["Mark"] == before["Mark"] + 3
    assert after["Payment"] == before["Payment"] + 1
    with SessionLocal() as db:
        ravi = db.scalar(select(Student).where(Student.name == "Ravi Kumar"))
        assert ravi.admission_no.startswith(f"{world['a']}") and ravi.legacy_id == "OLD-1" and str(ravi.dob) == "2013-03-12"
        m = db.scalar(select(Mark).where(Mark.student_id == ravi.id, Mark.exam == "UT1"))
        assert m.max_score == 25
        u = db.scalar(select(User).where(User.student_id == ravi.id))
        assert u.must_change and u.username == ravi.admission_no
    login_ok = client.post("/api/auth/login", json={"username": done["logins"][0]["login"], "password": done["logins"][0]["temp_password"]})
    assert login_ok.status_code == 200
    # the same file again creates nothing
    j2 = up(client, h, xlsx(SCHOOL_FILE)).json()
    again = run(client, h, j2["job_id"], {"sheets": cfgs(j2, year="2025-26")}, "confirm").json()
    assert again["imported"] is False and again["changes"] == 0
    assert counts() == after
    # undo removes exactly what the first import made
    batch = client.get("/api/import/batches", headers=h).json()[0]
    assert batch["can_undo"]
    assert client.post(f"/api/import/batches/{batch['id']}/undo", headers=h).status_code == 200
    assert counts() == before
    assert client.post(f"/api/import/batches/{batch['id']}/undo", headers=h).status_code == 409


def test_existing_students_are_matched_not_duplicated(client, world):
    h = login(client, "ownerA")
    rows = [STU, ["Asha Rao", "F", "2014-01-01", "5", "A", "Parent One", "9999999999", "ADM-9"]]
    j = up(client, h, xlsx({"Students": rows})).json()
    r = run(client, h, j["job_id"], {"sheets": cfgs(j)}).json()
    assert r["sheets"][0]["matched"] == 1 and r["sheets"][0]["new"] == 0 and r["totals"] == {}
    assert r["updated"] == {"students": 1}                       # only the old ID is remembered on the existing record
    run(client, h, j["job_id"], {"sheets": cfgs(j)}, "confirm")
    with SessionLocal() as db:
        assert db.scalar(select(Student.legacy_id).where(Student.id == world["s1"])) == "ADM-9"
        assert db.scalar(select(func.count()).select_from(Student).where(Student.school_id == world["a"])) == 2
    j2 = up(client, h, xlsx({"Students": rows})).json()          # second time: nothing left to do
    assert run(client, h, j2["job_id"], {"sheets": cfgs(j2)}).json()["changes"] == 0
    bid = client.get("/api/import/batches", headers=h).json()[0]["id"]
    client.post(f"/api/import/batches/{bid}/undo", headers=h)
    with SessionLocal() as db:
        assert db.scalar(select(Student.legacy_id).where(Student.id == world["s1"])) is None


def test_marks_by_name_with_ambiguity_and_bad_values(client, world):
    h = login(client, "ownerA")
    rows = [["Student", "Class", "Subject", "Exam", "Marks"],
            ["Asha Rao", "5", "Maths", "UT2", 20],
            ["Asha Rao", "5", "Maths", "UT2", 21],       # same cell, different value in the file
            ["Bala Rao", "5", "Maths", "UT2", 99],       # over the maximum
            ["Nobody", "5", "Maths", "UT2", 5],
            ["Bala Rao", "5", "Art", "UT2", 5],          # subject missing for the class
            ["Bala Rao", "5", "Maths", "Quiz", 5]]       # unknown exam
    j = up(client, h, xlsx({"Marks": rows})).json()
    r = run(client, h, j["job_id"], {"sheets": cfgs(j, year="2025-26")}).json()
    s = r["sheets"][0]
    msgs = " | ".join(e["message"] for e in s["errors"])
    assert s["new"] == 1 and s["error_count"] == 5 and not r["can_confirm"]
    for frag in ("twice", "outside 0-25", "No matching student", "no subject 'Art'", "not one of UT1"):
        assert frag in msgs
    assert run(client, h, j["job_id"], {"sheets": cfgs(j, year="2025-26")}, "confirm").status_code == 422
    assert counts()["Mark"] == 2                             # all-or-nothing: the one valid row was not saved


def test_same_name_in_two_classes_needs_a_tiebreaker(client, world):
    h = login(client, "ownerA")
    with SessionLocal() as db:
        db.add(Student(school_id=world["a"], admission_no="A3", name="Asha Rao", gender="Female", dob=__import__("datetime").date(2012, 1, 1),
                       grade="7", section="A", guardian_name="P", phone="9999999911"))
        db.commit()
    rows = [["Student", "Subject", "Exam", "Marks"], ["Asha Rao", "Maths", "UT2", 5]]
    j = up(client, h, xlsx({"Marks": rows})).json()
    r = run(client, h, j["job_id"], {"sheets": cfgs(j, year="2025-26")}).json()
    assert "2 students match" in r["sheets"][0]["errors"][0]["message"]


def test_conflicting_marks_kept_unless_update_chosen_and_undo_restores(client, world):
    h = login(client, "ownerA")
    rows = [["Student", "Class", "Subject", "Exam", "Marks"], ["Asha Rao", "5", "Maths", "UT1", 11]]   # system has 20
    j = up(client, h, xlsx({"Marks": rows})).json()
    keep = run(client, h, j["job_id"], {"sheets": cfgs(j, year="2025-26")}).json()
    assert keep["changes"] == 0 and keep["sheets"][0]["conflicts"]
    body = {"sheets": cfgs(j, year="2025-26", on_duplicate="update")}
    assert run(client, h, j["job_id"], body).json()["updated"] == {"marks": 1}
    run(client, h, j["job_id"], body, "confirm")
    with SessionLocal() as db:
        assert db.scalar(select(Mark.score).where(Mark.student_id == world["s1"], Mark.exam == "UT1")) == 11
    bid = client.get("/api/import/batches", headers=h).json()[0]["id"]
    client.post(f"/api/import/batches/{bid}/undo", headers=h)
    with SessionLocal() as db:
        assert db.scalar(select(Mark.score).where(Mark.student_id == world["s1"], Mark.exam == "UT1")) == 20


def test_payments_never_exceed_fee_and_repeat_import_adds_nothing(client, world):
    h = login(client, "ownerA")
    rows = [["Adm", "Amount", "Date"], ["A1", 5000, "01/04/2025"], ["A2", 99999, "01/04/2025"]]
    with SessionLocal() as db:
        db.execute(Student.__table__.update().where(Student.id == world["s1"]).values(legacy_id="A1"))
        db.execute(Student.__table__.update().where(Student.id == world["s2"]).values(legacy_id="A2"))
        db.commit()
    j = up(client, h, xlsx({"Receipts": [["Student ID", "Amount Paid", "Payment Date"]] + rows[1:]}), "r.xlsx").json()
    assert j["sheets"][0]["kind"] == "payments"
    r = run(client, h, j["job_id"], {"sheets": cfgs(j, year="2025-26")}).json()
    assert r["sheets"][0]["new"] == 1 and "past the" in r["sheets"][0]["errors"][0]["message"]


def test_sheet_without_required_columns_is_blocked(client, world):
    h = login(client, "ownerA")
    j = up(client, h, xlsx({"Students": [["name", "dob", "guardian"], ["A B", "2014-01-01", "X"]]})).json()
    r = run(client, h, j["job_id"], {"sheets": cfgs(j)}).json()
    assert not r["can_confirm"] and any("Gender" in b or "Class" in b for b in r["blockers"])


def test_plan_limit_enforced(client, world):
    h = login(client, "ownerA")
    with SessionLocal() as db:
        db.get(School, world["a"]).max_students = 2
        db.commit()
    rows = [STU, ["Ravi Kumar", "M", "12/03/2013", "6", "A", "Suresh Kumar", "9000000001", "1"]]
    j = up(client, h, xlsx({"Students": rows})).json()
    r = run(client, h, j["job_id"], {"sheets": cfgs(j)}).json()
    assert not r["can_confirm"] and "plan allows" in r["blockers"][0]
    assert run(client, h, j["job_id"], {"sheets": cfgs(j)}, "confirm").status_code == 422


def test_staff_import_creates_logins_and_matches_existing(client, world):
    h = login(client, "ownerA")
    rows = [["Name", "Gender", "Designation", "Email", "Phone", "Subjects", "Qualification"],
            ["Teacher One", "Male", "Teacher", "t@x.com", "9999999996", "Maths", "B.Ed"],            # already exists
            ["Meena Iyer", "Female", "Principal", "m@x.com", "9000000005", "English", "M.Ed"]]
    j = up(client, h, xlsx({"Staff": rows})).json()
    assert j["sheets"][0]["kind"] == "staff"
    r = run(client, h, j["job_id"], {"sheets": cfgs(j)}, "confirm").json()
    assert r["sheets"][0]["matched"] == 1 and r["totals"] == {"staff": 1}
    assert r["logins"][0]["login"].endswith("p001") or "p" in r["logins"][0]["login"]
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.username == r["logins"][0]["login"]))
        assert u.role == "staff" and u.must_change and "fees.view" in u.permissions
    nologin = up(client, h, xlsx({"Staff": rows[:1] + [["Zed Zee", "Male", "Teacher", "z@x.com", "9000000006", "", ""]]})).json()
    r2 = run(client, h, nologin["job_id"], {"sheets": cfgs(nologin), "create_logins": False}, "confirm").json()
    assert r2["logins"] == [] and r2["totals"] == {"staff": 1}


# ---------- permissions, isolation, lock ----------
def test_permissions(client, world):
    f = xlsx({"Students": [STU, ["Ravi Kumar", "M", "12/03/2013", "6", "A", "Suresh Kumar", "9000000001", "1"]]})
    for who in ("plainA", "kid1"):
        assert up(client, login(client, who), f).status_code == 403, who
    t = login(client, "teacherA")                      # marks.edit only: may upload, but not import students
    jt = up(client, t, f).json()
    assert run(client, t, jt["job_id"], {"sheets": cfgs(jt)}).status_code == 403
    assert client.post("/api/import/upload", content=f).status_code == 401
    # a staff member with only students.manage can import students but not fees
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.username == "ownerA"))
        db.add(User(school_id=world["a"], username="mgr", role="staff", full_name="M", permissions="students.manage",
                    password_hash=owner.password_hash, recovery_hashes=owner.recovery_hashes,
                    recovery_q=owner.recovery_q))
        db.commit()
    h = login(client, "mgr")
    j = up(client, h, xlsx({**{"Students": [STU, ["Ravi Kumar", "M", "12/03/2013", "6", "A", "Suresh Kumar", "9000000001", "1"]]},
                            "Fees": SCHOOL_FILE["Fees"]})).json()
    assert run(client, h, j["job_id"], {"sheets": cfgs(j)}).status_code == 403
    only = [c for c in cfgs(j) if c["kind"] == "students"]
    assert run(client, h, j["job_id"], {"sheets": only}).status_code == 200


def test_other_school_cannot_use_or_undo(client, world):
    a, b = login(client, "ownerA"), login(client, "ownerB")
    j = up(client, a, xlsx(SCHOOL_FILE)).json()
    body = {"sheets": cfgs(j, year="2025-26")}
    assert run(client, b, j["job_id"], body).status_code == 404
    assert run(client, b, j["job_id"], body, "confirm").status_code == 404
    assert client.delete(f"/api/import/jobs/{j['job_id']}", headers=b).status_code == 404
    run(client, a, j["job_id"], body, "confirm")
    bid = client.get("/api/import/batches", headers=a).json()[0]["id"]
    assert client.get("/api/import/batches", headers=b).json() == []
    assert client.post(f"/api/import/batches/{bid}/undo", headers=b).status_code == 404
    with SessionLocal() as db:   # school B untouched
        assert db.scalar(select(func.count()).select_from(Student).where(Student.school_id == world["b"])) == 1


def test_expired_subscription_blocks_writes_but_allows_reading_batches(client, world):
    from datetime import date, timedelta
    h = login(client, "ownerA")
    j = up(client, h, xlsx(SCHOOL_FILE)).json()
    with SessionLocal() as db:
        db.get(School, world["a"]).subscription_end = date.today() - timedelta(days=60)
        db.commit()
    assert run(client, h, j["job_id"], {"sheets": cfgs(j)}, "confirm").status_code == 403
    assert client.get("/api/import/batches", headers=h).status_code == 200


def test_undo_window_and_job_expiry(client, world):
    from datetime import timedelta
    h = login(client, "ownerA")
    j = up(client, h, xlsx(SCHOOL_FILE)).json()
    body = {"sheets": cfgs(j, year="2025-26")}
    run(client, h, j["job_id"], body, "confirm")
    with SessionLocal() as db:
        b = db.scalar(select(ImportBatch))
        b.created_at = b.created_at - timedelta(days=8)
        db.commit()
        bid = b.id
    listed = client.get("/api/import/batches", headers=h).json()[0]
    assert not listed["can_undo"]
    assert client.post(f"/api/import/batches/{bid}/undo", headers=h).status_code == 409
    j2 = up(client, h, xlsx(SCHOOL_FILE)).json()
    from app.models import ImportJob
    with SessionLocal() as db:
        jb = db.get(ImportJob, j2["job_id"])
        jb.created_at = jb.created_at - timedelta(hours=30)
        db.commit()
    assert run(client, h, j2["job_id"], body).status_code == 404


def test_validation_of_the_request(client, world):
    h = login(client, "ownerA")
    j = up(client, h, xlsx(SCHOOL_FILE)).json()
    good = cfgs(j)[0]
    bad_cases = [
        {**good, "kind": "nonsense"},
        {**good, "mapping": {"nope": 0}},
        {**good, "mapping": {"name": 99}},
        {**good, "mapping": {"name": 0, "gender": 0}},          # one column for two fields
        {**good, "header_row": 50},
    ]
    for bad in bad_cases:
        assert run(client, h, j["job_id"], {"sheets": [bad]}).status_code in (403, 422), bad
    assert run(client, h, j["job_id"], {"sheets": [good, good]}).status_code == 422
    assert run(client, h, j["job_id"], {"sheets": []}).status_code == 422
    assert run(client, h, 999999, {"sheets": [good]}).status_code == 404


def test_upload_limits_and_safe_errors(client, world):
    h = login(client, "ownerA")
    assert up(client, h, b"").status_code == 422
    assert up(client, h, b"x" * (si.MAX_FILE + 1)).status_code == 413
    r = up(client, h, b"PK\x03\x04junk")
    assert r.status_code == 422 and "Traceback" not in r.text


def test_formula_like_cells_are_stored_as_text_and_no_password_is_imported(client, world):
    h = login(client, "ownerA")
    rows = [STU + ["password"], ["+cmd Evil Kid", "M", "12/03/2013", "6", "A", "Suresh Kumar", "9000000001", "1", "hunter2hunter2"]]
    j = up(client, h, xlsx({"Students": rows})).json()
    r = run(client, h, j["job_id"], {"sheets": cfgs(j)}, "confirm").json()
    pw = r["logins"][0]["temp_password"]
    assert pw != "hunter2hunter2"
    with SessionLocal() as db:
        assert db.scalar(select(Student.name).where(Student.name.like("%Evil%"))) == "+cmd Evil Kid"   # plain text; exports defuse it
    assert client.post("/api/auth/login", json={"username": r["logins"][0]["login"], "password": "hunter2hunter2"}).status_code == 401
