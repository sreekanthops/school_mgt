import os
import tempfile

# Must be set before the app is imported
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["JWT_SECRET"] = "test-secret-not-used-in-prod-0123456789abcdef"

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Chapter, Event, Fee, Mark, Payment, School, Staff, Student, Subject, User
from app.security import hash_password

storage.UPLOAD_DIR = __import__("pathlib").Path(_tmp) / "uploads"
PW = "Passw0rd-Test!"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _user(db, **kw):
    # Pre-populate recovery_hashes so test users are not gated by the mandatory-setup check.
    # (Real users set these up on first login; test users are seeded as fully operational.)
    if "recovery_hashes" not in kw and kw.get("role") not in ("student", "superadmin"):
        from app.security import hash_password as hp
        from app.routers.recovery import norm
        kw["recovery_hashes"] = [hp(norm("testanswer")), hp(norm("testanswer2")), hp(norm("testanswer3"))]
        kw.setdefault("recovery_q", "0,1,2")
    u = User(password_hash=hash_password(PW), **kw)
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def world():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    a, b = School(name="School A"), School(name="School B")
    db.add_all([a, b])
    db.flush()
    from datetime import date
    sub_a = Subject(school_id=a.id, name="Maths", grade="5")
    sub_b = Subject(school_id=b.id, name="Maths", grade="5")
    db.add_all([sub_a, sub_b])
    db.flush()
    db.add(Chapter(subject_id=sub_a.id, number=1, title="Numbers"))
    s1 = Student(school_id=a.id, admission_no="A1", name="Asha Rao", gender="Female", dob=date(2014, 1, 1),
                 grade="5", section="A", guardian_name="Parent One", phone="9999999999")
    s2 = Student(school_id=a.id, admission_no="A2", name="Bala Rao", gender="Male", dob=date(2014, 2, 2),
                 grade="5", section="A", guardian_name="Parent Two", phone="9999999998")
    sb = Student(school_id=b.id, admission_no="A1", name="Other School Kid", gender="Male", dob=date(2014, 3, 3),
                 grade="5", section="A", guardian_name="Parent B", phone="9999999997")
    db.add_all([s1, s2, sb])
    db.flush()
    for st in (s1, s2):
        db.add(Mark(student_id=st.id, subject_id=sub_a.id, exam="UT1", academic_year="2025-26", score=20, max_score=25))
        db.add(Fee(student_id=st.id, academic_year="2025-26", total_amount=40000))
        db.add(Payment(student_id=st.id, academic_year="2025-26", amount=10000, paid_on=date.today(),
                       mode="Cash", receipt_no=f"R-{st.id}"))
    db.add(Staff(school_id=a.id, employee_id="E1", name="Teacher One", gender="Male", designation="Teacher",
                 department="Primary", qualification="B.Ed", experience_years=5, subjects="Maths", phone="9999999996",
                 email="t@x.com", joined_on=date(2020, 1, 1)))
    db.add(Event(school_id=a.id, title="Only A event", description="d", date=date.today(), location="L", category="C"))
    _user(db, username="super", role="superadmin", full_name="Super")
    _user(db, school_id=a.id, username="ownerA", role="admin", full_name="Owner A")
    _user(db, school_id=b.id, username="ownerB", role="admin", full_name="Owner B")
    _user(db, school_id=a.id, username="teacherA", role="staff", full_name="Teacher A", permissions="students.view,marks.edit,attendance.manage")
    _user(db, school_id=a.id, username="plainA", role="staff", full_name="Plain Staff", permissions="")
    _user(db, school_id=a.id, username="kid1", role="student", full_name="Asha Rao", student_id=s1.id)
    db.commit()
    ids = {"a": a.id, "b": b.id, "s1": s1.id, "s2": s2.id, "sb": sb.id, "sub_a": sub_a.id, "sub_b": sub_b.id}
    db.close()
    return ids


@pytest.fixture()
def client():
    from app import security
    security._fails.clear()
    security._hits.clear()
    return TestClient(app)


def login(client, username, password=PW):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def onboard(client, username, temp_password, own_pw=None):
    """Complete the mandatory new-user setup for non-student accounts:
    1) Change the temporary password.
    2) Set up recovery questions.
    Returns auth headers usable for normal API calls.
    """
    if own_pw is None:
        own_pw = temp_password + "Own1"
    h = login(client, username, temp_password)
    assert client.post("/api/auth/password", headers=h,
                       json={"current_password": temp_password, "new_password": own_pw}).status_code == 204
    h = login(client, username, own_pw)
    qs = client.get("/api/auth/recovery/setup", headers=h).json()["questions"]
    body = {"current_password": own_pw,
            "answers": [{"id": q["id"], "answer": a}
                        for q, a in zip(qs, ("Fluffy", "Oak Lane", "Maria"))]}
    assert client.post("/api/auth/recovery/setup", headers=h, json=body).status_code == 204
    return login(client, username, own_pw)
