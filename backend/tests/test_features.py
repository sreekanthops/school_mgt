"""Announcements, exports, bulk import / new year, billing, staff logins and attendance."""
import io
from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Attendance, Invoice, School, Student, User
from .conftest import PW, login

BODY = {"employee_id": "HACK", "name": "New Teacher", "gender": "Female", "designation": "Teacher", "department": "Primary",
        "qualification": "M.Ed", "experience_years": 3, "phone": "9999999990", "email": "n@x.com", "joined_on": "2024-06-01"}


def _h(client, name):
    return login(client, name)


# ---------- announcements ----------
def test_announcements_audience_rules(client, world):
    o, t, k = _h(client, "ownerA"), _h(client, "teacherA"), _h(client, "kid1")
    mk = lambda **kw: client.post("/api/announcements", headers=o, json={"title": "Hello", "body": "text", **kw})
    assert mk().status_code == 201
    assert mk(title="Staff only", audience="staff").status_code == 201
    assert mk(title="Class 5 only", audience="class", grade="5").status_code == 201
    assert mk(title="Class 9 only", audience="class", grade="9").status_code == 201
    assert mk(audience="class").status_code == 422                       # class needs a class
    assert mk(audience="everyone").status_code == 422
    titles = lambda h: {a["title"] for a in client.get("/api/announcements", headers=h).json()}
    assert titles(k) == {"Hello", "Class 5 only"}                         # kid1 is in class 5: no staff-only, no class 9
    assert titles(t) >= {"Hello", "Staff only"}
    # only people with announcements.manage can post, edit or delete
    assert client.post("/api/announcements", headers=t, json={"title": "Nope", "body": "x"}).status_code == 403
    assert client.post("/api/announcements", headers=k, json={"title": "Nope", "body": "x"}).status_code == 403
    aid = client.get("/api/announcements", headers=o).json()[0]["id"]
    assert client.delete(f"/api/announcements/{aid}", headers=t).status_code == 403


def test_announcements_isolated_and_unread_counts(client, world):
    o, k, ob = _h(client, "ownerA"), _h(client, "kid1"), _h(client, "ownerB")
    a = client.post("/api/announcements", headers=o, json={"title": "Hi", "body": "x"}).json()
    assert client.get("/api/announcements", headers=ob).json() == []
    assert client.delete(f"/api/announcements/{a['id']}", headers=ob).status_code == 404
    assert client.get("/api/announcements/unread", headers=k).json() == {"count": 1}
    assert client.get("/api/announcements/unread", headers=o).json() == {"count": 0}   # own posts are already read
    assert client.post("/api/announcements/read-all", headers=k).status_code == 204
    assert client.get("/api/announcements/unread", headers=k).json() == {"count": 0}
    assert client.post("/api/announcements/read-all", headers=k).status_code == 204     # idempotent


def test_announcement_html_is_stored_as_text(client, world):
    o = _h(client, "ownerA")
    r = client.post("/api/announcements", headers=o, json={"title": "<b>x</b>", "body": "<script>alert(1)</script>"})
    assert r.status_code == 201 and r.json()["body"] == "<script>alert(1)</script>"   # the UI renders text, never HTML
    assert client.post("/api/announcements", headers=o, json={"title": "  ", "body": "x"}).status_code == 422


# ---------- exports ----------
def test_csv_exports_and_formula_injection(client, world):
    o = _h(client, "ownerA")
    db = SessionLocal()
    s = db.get(Student, world["s1"])
    s.name = "=cmd|calc"
    db.commit()
    db.close()
    r = client.get("/api/export/students", headers=o)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    assert "'=cmd|calc" in text and ",=cmd" not in text          # neutralised
    assert "Other School Kid" not in text                         # other school's data never appears
    assert text.splitlines()[0].startswith("Student ID,Name")
    assert "Asha" not in client.get("/api/export/students?grade=9", headers=o).content.decode()


def test_pdf_exports_and_report_card(client, world):
    o, k = _h(client, "ownerA"), _h(client, "kid1")
    for url in ("/api/export/students?format=pdf", "/api/export/marks?format=pdf&year=2025-26",
                "/api/export/fees?format=pdf&year=2025-26", f"/api/students/{world['s1']}/report-card?year=2025-26"):
        r = client.get(url, headers=o)
        assert r.status_code == 200 and r.content[:5] == b"%PDF-", url
    assert client.get(f"/api/students/{world['s1']}/report-card?year=2025-26", headers=k).content[:5] == b"%PDF-"
    assert client.get(f"/api/students/{world['s2']}/report-card?year=2025-26", headers=k).status_code == 403
    assert client.get(f"/api/students/{world['sb']}/report-card", headers=o).status_code == 404   # other school
    assert client.get("/api/export/marks?format=xml", headers=o).status_code == 422


def test_export_permissions(client, world):
    t, p, k = _h(client, "teacherA"), _h(client, "plainA"), _h(client, "kid1")
    assert client.get("/api/export/students", headers=t).status_code == 200          # students.view
    assert client.get("/api/export/fees", headers=t).status_code == 403              # no fees permission
    assert client.get("/api/export/students", headers=p).status_code == 403
    assert client.get("/api/export/students", headers=k).status_code == 403
    assert client.get("/api/export/marks", headers=k).status_code == 403


def test_fee_receipt_access(client, world):
    o, k = _h(client, "ownerA"), _h(client, "kid1")
    pays = client.get(f"/api/students/{world['s1']}/fees", headers=o).json()["payments"]
    pid = pays[0]["id"]
    assert client.get(f"/api/students/{world['s1']}/payments/{pid}/receipt", headers=o).content[:5] == b"%PDF-"
    assert client.get(f"/api/students/{world['s1']}/payments/{pid}/receipt", headers=k).content[:5] == b"%PDF-"
    pid2 = client.get(f"/api/students/{world['s2']}/fees", headers=o).json()["payments"][0]["id"]
    assert client.get(f"/api/students/{world['s2']}/payments/{pid2}/receipt", headers=k).status_code == 403
    # a payment id of another student cannot be fetched through your own student URL
    assert client.get(f"/api/students/{world['s1']}/payments/{pid2}/receipt", headers=o).status_code == 404
    assert client.get(f"/api/students/{world['s1']}/payments/{pid}/receipt", headers=_h(client, "teacherA")).status_code == 403


# ---------- bulk import ----------
SHEET = ("name,gender,dob,class,section,guardian_name,phone,email,blood_group,address\n"
         "Meera Nair,F,21/06/2014,Class 5,a,Ravi Nair,9876543210,m@x.com,o+,12 Main Rd\n"
         "Arjun Das,Male,2013-02-02,6,B,Kiran Das,9876543211,,,\n"
         "Tiny Tot,Female,2021-05-05,LKG,A,Anu Tot,9876543212,,,\n")


def _post(client, h, body, dry=True):
    return client.post(f"/api/students/import?dry_run={'true' if dry else 'false'}", headers=h, content=body)


def test_import_dry_run_then_commit(client, world):
    o = _h(client, "ownerA")
    d = _post(client, o, SHEET).json()
    assert d["valid"] == 3 and d["errors"] == [] and d["imported"] == 0
    db = SessionLocal()
    before = len(db.scalars(select(Student)).all())
    db.close()
    r = _post(client, o, SHEET, dry=False)
    assert r.status_code == 200 and r.json()["imported"] == 3
    y = date.today().year
    ids = {x["name"]: x["student_id"] for x in r.json()["logins"]}
    assert ids["Meera Nair"] == f"{world['a']}{y}s05001" and ids["Tiny Tot"] == f"{world['a']}{y}s90001"
    db = SessionLocal()
    assert len(db.scalars(select(Student)).all()) == before + 3
    u = db.scalar(select(User).where(User.username == ids["Meera Nair"]))
    assert u.must_change and u.role == "student"
    st = db.get(Student, u.student_id)
    assert (st.gender, st.section, st.blood_group, str(st.dob)) == ("Female", "A", "O+", "2014-06-21")
    db.close()
    pw = {x["student_id"]: x["temp_password"] for x in r.json()["logins"]}[ids["Meera Nair"]]
    assert client.post("/api/auth/login", json={"username": ids["Meera Nair"], "password": pw}).status_code == 200
    # importing the same file again is refused as duplicates, not silently doubled
    again = _post(client, o, SHEET).json()
    assert again["valid"] == 0 and len(again["errors"]) == 3 and "already exists" in again["errors"][0]["message"]


def test_import_validation_is_all_or_nothing(client, world):
    o = _h(client, "ownerA")
    bad = SHEET + "Bad Row,Female,2999-01-01,5,A,Parent,12,,,\nNo Class,Male,2014-01-01,13,A,Parent,9876543210,,,\n"
    d = _post(client, o, bad).json()
    assert d["valid"] == 3 and len(d["errors"]) == 2 and d["errors"][0]["row"] == 5
    r = _post(client, o, bad, dry=False)
    assert r.status_code == 422
    db = SessionLocal()
    assert db.scalar(select(Student).where(Student.name == "Meera Nair")) is None
    db.close()


def test_import_rejects_bad_files_and_enforces_permissions(client, world):
    o, t, k = _h(client, "ownerA"), _h(client, "teacherA"), _h(client, "kid1")
    assert _post(client, o, b"").status_code == 422
    assert _post(client, o, b"name,gender\nA,F\n").status_code == 422                     # missing columns named in the message
    assert "dob" in _post(client, o, b"name,gender\nA,F\n").json()["detail"]
    assert _post(client, o, b"\xff\xfe\x00bad").status_code == 422
    assert _post(client, o, b"PK\x03\x04garbage").status_code == 422                       # not a real xlsx
    assert _post(client, o, b"x" * (2 * 1024 * 1024 + 10)).status_code == 413
    many = SHEET.splitlines()[0] + "\n" + "\n".join(f"S{n} Name,Male,2014-01-01,5,A,Parent X,9876543210,,," for n in range(301))
    assert _post(client, o, many).status_code == 422
    assert _post(client, t, SHEET).status_code == 403 and _post(client, k, SHEET).status_code == 403


def test_import_xlsx(client, world):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in [r.split(",") for r in SHEET.strip().splitlines()]:
        ws.append(row)
    ws["C2"] = date(2014, 6, 21)
    buf = io.BytesIO()
    wb.save(buf)
    d = _post(client, _h(client, "ownerA"), buf.getvalue()).json()
    assert d["valid"] == 3 and d["errors"] == []


def test_import_respects_plan_limit(client, world):
    db = SessionLocal()
    db.get(School, world["a"]).max_students = 3
    db.commit()
    db.close()
    r = _post(client, _h(client, "ownerA"), SHEET, dry=False)
    assert r.status_code == 403 and "plan allows" in r.json()["detail"]


def test_import_template(client, world):
    r = client.get("/api/students/import/template", headers=_h(client, "ownerA"))
    assert r.status_code == 200 and r.text.startswith("name,gender,dob,class,section")


# ---------- new academic year / promotion ----------
def test_new_year_promotes_and_holds_back(client, world):
    o = _h(client, "ownerA")
    pre = client.get("/api/school/new-year", headers=o).json()
    assert pre["current_year"] == "2025-26" and pre["next_year"] == "2026-27"
    r = client.post("/api/school/new-year", headers=o, json={"year": "2026-27", "hold_back": [world["s2"]]})
    assert r.status_code == 200 and r.json()["promoted"] == 1 and r.json()["held_back"] == 1
    d = client.get(f"/api/students/{world['s1']}", headers=o).json()
    assert d["student"]["grade"] == "6" and d["selected_year"] == "2026-27"
    assert "2025-26" in d["years"]                                   # last year's marks stay available
    assert client.get(f"/api/students/{world['s2']}", headers=o).json()["student"]["grade"] == "5"
    # a second click does not promote again
    assert client.post("/api/school/new-year", headers=o, json={"year": "2026-27"}).status_code == 409
    # other school is untouched
    assert client.get(f"/api/students/{world['sb']}", headers=_h(client, "ownerB")).json()["student"]["grade"] == "5"


def test_new_year_class10_and_permissions(client, world):
    o, t = _h(client, "ownerA"), _h(client, "teacherA")
    db = SessionLocal()
    db.get(Student, world["s1"]).grade = "10"
    db.commit()
    db.close()
    r = client.post("/api/school/new-year", headers=o, json={"year": "2026-27", "remove_graduates": True}).json()
    assert r["class10_removed"] == 1
    assert client.get(f"/api/students/{world['s1']}", headers=o).status_code == 404
    assert client.post("/api/school/new-year", headers=t, json={"year": "2027-28"}).status_code == 403
    assert client.post("/api/school/new-year", headers=o, json={"year": "2027-28", "hold_back": [world["sb"]]}).status_code == 422


def test_bulk_class_fee(client, world):
    o, t = _h(client, "ownerA"), _h(client, "teacherA")
    assert client.put("/api/fees/bulk", headers=o, json={"year": "2025-26", "grade": "5", "total_amount": 55000}).json() == {"students": 2}
    assert client.get(f"/api/students/{world['s1']}/fees", headers=o).json()["total"] == 55000
    assert client.get(f"/api/students/{world['sb']}/fees", headers=_h(client, "ownerB")).json()["total"] == 0
    assert client.put("/api/fees/bulk", headers=t, json={"year": "2025-26", "grade": "5", "total_amount": 1}).status_code == 403


# ---------- staff login on creation ----------
def test_add_staff_creates_login(client, world):
    o, a, y = _h(client, "ownerA"), world["a"], date.today().year
    r = client.post("/api/staff", headers=o, json=BODY)
    assert r.status_code == 201
    lg = r.json()["login"]
    assert lg["username"] == r.json()["employee_id"] == f"{a}{y}t001"
    assert set(lg["permissions"]) == {"students.view", "marks.edit", "attendance.manage"}
    # first sign-in works but is locked to a password change
    tok = client.post("/api/auth/login", json={"username": lg["username"], "password": lg["temp_password"]})
    assert tok.status_code == 200
    h = {"Authorization": f"Bearer {tok.json()['token']}"}
    assert client.get("/api/students", headers=h).status_code == 403
    p = client.post("/api/staff", headers=o, json={**BODY, "name": "Head Person", "designation": "Principal"}).json()
    assert p["login"]["username"].endswith("p001") and "fees.view" in p["login"]["permissions"]
    assert "users.manage" not in p["login"]["permissions"]
    n = client.post("/api/staff?create_login=false", headers=o, json={**BODY, "name": "No Login"}).json()
    assert n["login"] is None


def test_staff_login_never_exceeds_creator_and_goes_with_delete(client, world):
    db = SessionLocal()
    from app.models import User as U
    helper = db.scalar(select(U).where(U.username == "plainA"))
    helper.permissions = "staff.manage"
    db.commit()
    db.close()
    r = client.post("/api/staff", headers=_h(client, "plainA"), json=BODY).json()
    assert r["login"]["permissions"] == []                           # the creator holds none of the defaults
    o = _h(client, "ownerA")
    assert client.delete(f"/api/staff/{r['id']}", headers=o).status_code == 204
    db = SessionLocal()
    assert db.scalar(select(U).where(U.username == r["employee_id"])) is None
    db.close()


# ---------- attendance ----------
def _sheet(client, h, status="P", day=None, grade="5", section="A"):
    day = day or date.today().isoformat()
    sh = client.get(f"/api/attendance/sheet?grade={grade}&section={section}&day={day}", headers=h).json()
    return client.put("/api/attendance/sheet", headers=h, json={
        "grade": grade, "section": section, "day": day, "entries": [{"student_id": s["id"], "status": status} for s in sh["students"]]})


def test_mark_attendance_and_edit(client, world):
    t = _h(client, "teacherA")
    sh = client.get("/api/attendance/sheet?grade=5&section=A", headers=t).json()
    assert [s["name"] for s in sh["students"]] == ["Asha Rao", "Bala Rao"] and not sh["marked"]
    assert _sheet(client, t, "P").json() == {"saved": 2}
    sid = world["s2"]
    day = date.today().isoformat()
    assert client.put("/api/attendance/sheet", headers=t, json={"grade": "5", "section": "A", "day": day,
                      "entries": [{"student_id": sid, "status": "A"}]}).status_code == 200
    sh = client.get("/api/attendance/sheet?grade=5&section=A", headers=t).json()
    assert sh["marked"] and {s["id"]: s["status"] for s in sh["students"]}[sid] == "A"
    db = SessionLocal()
    assert len(db.scalars(select(Attendance).where(Attendance.day == date.today())).all()) == 2   # updated, not duplicated
    db.close()


def test_attendance_validation_and_permissions(client, world):
    t, p, k, o = _h(client, "teacherA"), _h(client, "plainA"), _h(client, "kid1"), _h(client, "ownerA")
    day = date.today().isoformat()
    put = lambda h, **kw: client.put("/api/attendance/sheet", headers=h, json={"grade": "5", "section": "A", "day": day, **kw})
    assert put(t, entries=[{"student_id": world["s1"], "status": "X"}]).status_code == 422
    assert put(t, entries=[{"student_id": world["sb"], "status": "P"}]).status_code == 422          # other school's student
    assert _sheet(client, t, day=(date.today() + timedelta(days=1)).isoformat()).status_code == 422  # future
    assert _sheet(client, t, day=(date.today() - timedelta(days=200)).isoformat()).status_code == 422  # too old
    assert put(p, entries=[]).status_code == 403 and put(k, entries=[]).status_code == 403
    assert client.get("/api/attendance/sheet?grade=5&section=A", headers=k).status_code == 403
    assert client.get("/api/attendance/sheet?grade=99&section=A", headers=o).status_code == 422
    # owner B cannot see school A's class through the same URL
    assert client.get("/api/attendance/sheet?grade=5&section=A", headers=_h(client, "ownerB")).json()["students"][0]["name"] == "Other School Kid"


def _fill(world, pattern: str, sid: int):
    """pattern: one char per school day going back from today, newest first."""
    db = SessionLocal()
    for n, ch in enumerate(pattern):
        db.add(Attendance(school_id=world["a"], student_id=sid, day=date.today() - timedelta(days=n), status=ch))
    db.commit()
    db.close()


def test_low_attendance_alerts_and_student_view(client, world):
    o, k, t = _h(client, "ownerA"), _h(client, "kid1"), _h(client, "teacherA")
    _fill(world, "PAPAPAPAPAPAPA", world["s1"])        # 7 of 14 -> 50%
    _fill(world, "PPPPPPPPPPPPPP", world["s2"])        # 100%
    al = client.get("/api/attendance/alerts", headers=o).json()
    assert [x["id"] for x in al["items"]] == [world["s1"]] and al["items"][0]["reason"] == "low"
    assert al["items"][0]["pct"] == 50.0
    mine = client.get(f"/api/students/{world['s1']}/attendance", headers=k).json()
    assert mine["low"] and mine["month"]["pct"] == 50.0
    assert client.get(f"/api/students/{world['s2']}/attendance", headers=k).status_code == 403
    assert client.get(f"/api/students/{world['s2']}/attendance", headers=t).status_code == 200
    assert client.get("/api/attendance/alerts", headers=k).status_code == 403
    # the dashboard carries the same flag for staff
    dash = client.get("/api/dashboard", headers=o).json()
    assert [x["id"] for x in dash["attendance_alerts"]] == [world["s1"]]


def test_absence_streak_flagged_even_with_few_days(client, world):
    _fill(world, "AAAP", world["s2"])                  # 3 absent in a row, only 4 days recorded
    items = client.get("/api/attendance/alerts", headers=_h(client, "ownerA")).json()["items"]
    assert items[0]["id"] == world["s2"] and items[0]["reason"] == "streak"


def test_attendance_report_and_export(client, world):
    o = _h(client, "ownerA")
    _fill(world, "PPAL", world["s1"])
    r = client.get("/api/attendance/report?grade=5", headers=o).json()
    row = next(i for i in r["items"] if i["id"] == world["s1"])
    assert (row["present"], row["late"], row["absent"], row["pct"]) == (2, 1, 1, 75.0)   # late counts as attended
    assert len(r["trend"]) == 4
    assert client.get("/api/attendance/report?from=2025-01-01&to=2027-12-31", headers=o).status_code == 422
    assert client.get("/api/attendance/report?from=2026-01-02&to=2026-01-01", headers=o).status_code == 422
    c = client.get("/api/export/attendance?grade=5", headers=o)
    assert c.headers["content-type"].startswith("text/csv") and "Asha Rao" in c.content.decode()
    assert "Other School Kid" not in c.content.decode()


def test_chatbot_attendance_answers(client, world):
    o, k = _h(client, "ownerA"), _h(client, "kid1")
    _fill(world, "PAPAPAPAPAPAPA", world["s1"])
    a = client.post("/api/chat", headers=o, json={"question": "who has low attendance?"}).json()
    assert "Asha Rao" in a["answer"]
    mine = client.post("/api/chat", headers=k, json={"question": "what is my attendance?"}).json()
    assert "50.0%" in mine["answer"]
    assert "don't have access" in client.post("/api/chat", headers=k, json={"question": "who has low attendance?"}).json()["answer"]
    n = client.post("/api/chat", headers=k, json={"question": "any announcements?"}).json()
    assert "announcement" in n["answer"].lower()


# ---------- billing ----------
def test_invoice_lifecycle_extends_subscription(client, world):
    sa = _h(client, "super")
    db = SessionLocal()
    db.get(School, world["a"]).subscription_end = date.today() + timedelta(days=10)
    db.get(School, world["a"]).plan = "Standard"
    db.commit()
    db.close()
    r = client.post(f"/api/schools/{world['a']}/invoices", headers=sa, json={})
    assert r.status_code == 201
    inv = r.json()
    assert inv["amount"] == 24000 and inv["tax"] == 4320 and inv["total"] == 28320 and inv["status"] == "Pending"
    assert inv["period_start"] == (date.today() + timedelta(days=11)).isoformat()      # starts the day after the current end
    assert inv["number"].startswith("INV-") and inv["number"][-5:] == f"{inv['id']:05d}"
    s = client.get("/api/billing/summary", headers=sa).json()
    assert s["pending"] == 28320 and s["collected"] == 0
    assert client.put(f"/api/invoices/{inv['id']}/pay", headers=sa, json={"mode": "Barter"}).status_code == 422
    paid = client.put(f"/api/invoices/{inv['id']}/pay", headers=sa, json={"mode": "UPI", "reference": "UTR1"})
    assert paid.json()["status"] == "Paid"
    db = SessionLocal()
    assert db.get(School, world["a"]).subscription_end.isoformat() == inv["period_end"]
    db.close()
    assert client.put(f"/api/invoices/{inv['id']}/pay", headers=sa, json={"mode": "UPI"}).status_code == 409      # not twice
    assert client.put(f"/api/invoices/{inv['id']}/cancel", headers=sa).status_code == 409
    assert client.get("/api/billing/summary", headers=sa).json()["collected"] == 28320
    assert client.get(f"/api/invoices/{inv['id']}/pdf", headers=sa).content[:5] == b"%PDF-"
    assert "INV-" in client.get("/api/invoices/export", headers=sa).content.decode()


def test_invoice_overdue_cancel_and_audit(client, world):
    sa = _h(client, "super")
    inv = client.post(f"/api/schools/{world['a']}/invoices", headers=sa,
                      json={"amount": 1000, "tax_pct": 0, "due_on": (date.today() - timedelta(days=3)).isoformat()}).json()
    assert inv["status"] == "Overdue" and inv["total"] == 1000
    assert client.get("/api/billing/summary", headers=sa).json()["overdue_count"] == 1
    assert client.put(f"/api/invoices/{inv['id']}/cancel", headers=sa).json()["status"] == "Cancelled"
    assert client.get("/api/billing/summary", headers=sa).json()["pending"] == 0
    actions = [a["action"] for a in client.get("/api/audit", headers=sa).json()]
    assert "invoice_created" in actions and "invoice_cancelled" in actions
    assert client.post(f"/api/schools/{world['a']}/invoices", headers=sa,
                       json={"period_start": "2026-05-01", "period_end": "2026-04-01"}).status_code == 422
    assert client.post("/api/schools/9999/invoices", headers=sa, json={}).status_code == 404


def test_billing_access_rules(client, world):
    sa, o, ob, t, k = _h(client, "super"), _h(client, "ownerA"), _h(client, "ownerB"), _h(client, "teacherA"), _h(client, "kid1")
    inv = client.post(f"/api/schools/{world['a']}/invoices", headers=sa, json={}).json()
    for h in (o, t, k):                                           # only the platform team issues or changes invoices
        assert client.post(f"/api/schools/{world['a']}/invoices", headers=h, json={}).status_code == 403
        assert client.put(f"/api/invoices/{inv['id']}/pay", headers=h, json={"mode": "UPI"}).status_code == 403
        assert client.get("/api/billing/summary", headers=h).status_code == 403
        assert client.get("/api/invoices", headers=h).status_code == 403
    mine = client.get("/api/billing/mine", headers=o).json()
    assert [i["id"] for i in mine["invoices"]] == [inv["id"]]
    assert client.get(f"/api/billing/mine/{inv['id']}/pdf", headers=o).content[:5] == b"%PDF-"
    assert client.get("/api/billing/mine", headers=ob).json()["invoices"] == []                  # other school sees nothing
    assert client.get(f"/api/billing/mine/{inv['id']}/pdf", headers=ob).status_code == 404
    assert client.get("/api/billing/mine", headers=t).status_code == 403                         # staff and students: owner only
    assert client.get("/api/billing/mine", headers=k).status_code == 403


def test_invoices_survive_school_deletion(client, world):
    sa = _h(client, "super")
    inv = client.post(f"/api/schools/{world['b']}/invoices", headers=sa, json={}).json()
    assert client.delete(f"/api/schools/{world['b']}", headers=sa).status_code == 204
    left = client.get("/api/invoices", headers=sa).json()
    assert [i["id"] for i in left] == [inv["id"]] and left[0]["school_name"] == "School B"


def test_new_columns_added_to_old_database():
    """A database created before a column existed gets that column on startup instead of failing."""
    from sqlalchemy import create_engine, inspect, text
    import app.db as appdb
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE schools (id INTEGER PRIMARY KEY, name VARCHAR(120))"))
    old, appdb.engine = appdb.engine, eng
    try:
        appdb.add_missing_columns()
    finally:
        appdb.engine = old
    assert "academic_year" in {c["name"] for c in inspect(eng).get_columns("schools")}


def test_locked_school_can_still_read_and_download(client, world):
    o = _h(client, "ownerA")
    client.post("/api/announcements", headers=o, json={"title": "Hi", "body": "x"})
    db = SessionLocal()
    db.get(School, world["a"]).subscription_end = date.today() - timedelta(days=1)
    db.commit()
    db.close()
    assert client.post("/api/announcements", headers=o, json={"title": "No", "body": "x"}).status_code == 403   # writes blocked
    assert client.post("/api/students/import?dry_run=false", headers=o, content=b"x").status_code == 403
    assert client.put("/api/attendance/sheet", headers=o, json={"grade": "5", "section": "A", "day": date.today().isoformat(), "entries": []}).status_code == 403
    assert client.post("/api/school/new-year", headers=o, json={"year": "2026-27"}).status_code == 403
    # reading, downloading and marking notices read stay available (the owner can still see everything)
    assert client.get("/api/export/students", headers=o).status_code == 200
    assert client.get(f"/api/students/{world['s1']}/report-card", headers=o).status_code == 200
    assert client.get("/api/billing/mine", headers=o).status_code == 200
    assert client.post("/api/announcements/read-all", headers=o).status_code == 204
    # students are never locked
    assert client.post("/api/announcements/read-all", headers=_h(client, "kid1")).status_code == 204
