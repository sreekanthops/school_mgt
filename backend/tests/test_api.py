from .conftest import PNG, PW, login


# ---------- tenant isolation ----------
def test_school_a_cannot_see_school_b_data(client, world):
    h = login(client, "ownerA")
    names = [s["name"] for s in client.get("/api/students?page_size=100", headers=h).json()["items"]]
    assert "Other School Kid" not in names and "Asha Rao" in names
    assert client.get(f"/api/students/{world['sb']}", headers=h).status_code == 404
    assert client.put(f"/api/students/{world['sb']}", headers=h, json={}).status_code in (404, 422)
    assert client.delete(f"/api/students/{world['sb']}", headers=h).status_code == 404
    assert client.get(f"/api/subjects/{world['sub_b']}", headers=h).status_code == 404
    assert client.delete(f"/api/subjects/{world['sub_b']}", headers=h).status_code == 404


def test_cannot_mark_into_other_school_subject(client, world):
    h = login(client, "ownerA")
    r = client.post(f"/api/students/{world['s1']}/marks", headers=h,
                    json={"subject_id": world["sub_b"], "exam": "UT1", "academic_year": "2025-26", "score": 5})
    assert r.status_code == 404


def test_new_school_starts_empty(client, world):
    h = login(client, "ownerB")
    d = client.get("/api/dashboard", headers=h).json()
    assert d["counts"]["students"] == 1 and d["counts"]["staff"] == 0 and d["counts"]["events"] == 0
    assert client.get("/api/events", headers=h).json()["items"] == []
    assert client.get("/api/staff", headers=h).json() == []


def test_cannot_manage_other_schools_users(client, world):
    h = login(client, "ownerB")
    uid = client.get("/api/users", headers=login(client, "ownerA")).json()[0]["id"]
    assert client.delete(f"/api/users/{uid}", headers=h).status_code == 404
    assert client.post(f"/api/users/{uid}/reset-password", headers=h).status_code == 404


# ---------- superadmin ----------
def test_superadmin_creates_school_and_owner_logs_in_to_empty_school(client, world):
    from datetime import date
    h = login(client, "super")
    r = client.post("/api/schools", headers=h, json={"name": "New Kids School", "owner_name": "New Owner"})
    assert r.status_code == 201
    temp = r.json()["owner"]["temp_password"]
    # the owner login is generated: <school id><year>o001
    owner_id = r.json()["owner"]["username"]
    assert owner_id == f"{r.json()['school']['id']}{date.today().year}o001"
    oh = login(client, owner_id, temp)
    assert client.get("/api/school", headers=oh).json()["name"] == "New Kids School"
    assert client.get("/api/dashboard", headers=oh).json()["counts"]["students"] == 0
    # owner can now rename their own school
    assert client.put("/api/school", headers=oh, json={"name": "Renamed School"}).json()["name"] == "Renamed School"


def test_superadmin_endpoints_forbidden_to_others(client, world):
    for u in ("ownerA", "teacherA", "kid1"):
        h = login(client, u)
        assert client.get("/api/schools", headers=h).status_code == 403
        assert client.post("/api/schools", headers=h, json={"name": "x", "owner_name": "yy"}).status_code == 403


def test_superadmin_cannot_use_school_data_endpoints(client, world):
    h = login(client, "super")
    assert client.get("/api/students", headers=h).status_code == 403


def test_disabled_school_blocks_login(client, world):
    h = login(client, "super")
    assert client.put(f"/api/schools/{world['b']}/active", headers=h, json={"active": False}).status_code == 200
    r = client.post("/api/auth/login", json={"username": "ownerB", "password": PW})
    assert r.status_code == 403


# ---------- permissions ----------
def test_staff_without_permission_cannot_write(client, world):
    h = login(client, "plainA")
    assert client.get("/api/students", headers=h).json()["detailed"] is False
    body = {"admission_no": "Z", "name": "Zed Zed", "gender": "Male", "dob": "2015-01-01", "grade": "5",
            "section": "A", "guardian_name": "Guardian", "phone": "9999999999"}
    assert client.post("/api/students", headers=h, json=body).status_code == 403
    assert client.post("/api/subjects", headers=h, json={"name": "Art", "grade": "5"}).status_code == 403
    assert client.post("/api/events", headers=h, json={"title": "T1", "description": "d", "date": "2026-01-01", "location": "L", "category": "Cc"}).status_code == 403
    assert client.get("/api/users", headers=h).status_code == 403


def test_teacher_can_enter_marks_but_not_see_fees_or_manage(client, world):
    h = login(client, "teacherA")
    r = client.post(f"/api/students/{world['s1']}/marks", headers=h,
                    json={"subject_id": world["sub_a"], "exam": "UT1", "academic_year": "2025-26", "score": 22})
    assert r.status_code == 201
    assert client.get(f"/api/students/{world['s1']}/fees", headers=h).status_code == 403
    assert client.get(f"/api/students/{world['s1']}", headers=h).json()["fees"] is None
    assert client.post(f"/api/students/{world['s1']}/payments", headers=h, json={"academic_year": "2025-26", "amount": 1, "mode": "Cash"}).status_code == 403
    d = client.get("/api/dashboard", headers=h).json()
    assert d["fees"] is None and d["top_defaulters"] == []


def test_score_cannot_exceed_max(client, world):
    h = login(client, "teacherA")
    r = client.post(f"/api/students/{world['s1']}/marks", headers=h,
                    json={"subject_id": world["sub_a"], "exam": "UT1", "academic_year": "2025-26", "score": 26})
    assert r.status_code == 422


def test_admin_can_delegate_user_management(client, world):
    h = login(client, "ownerA")
    r = client.post("/api/users", headers=h, json={"username": "mgr", "full_name": "Manager One", "role": "staff",
                                                   "permissions": ["users.manage", "students.view"]})
    assert r.status_code == 201
    assert client.post("/api/users", headers=h, json={"username": "bad", "full_name": "Bad Perm", "role": "staff",
                                                      "permissions": ["not.a.permission"]}).status_code == 422


def test_delegate_cannot_escalate(client, world):
    oh = login(client, "ownerA")
    r = client.post("/api/users", headers=oh, json={"username": "mgr", "full_name": "Manager One", "role": "staff",
                                                    "permissions": ["users.manage", "students.view"]})
    mh = login(client, "mgr", r.json()["temp_password"])
    mk = lambda u, role, perms: client.post("/api/users", headers=mh, json={
        "username": u, "full_name": "Some Person", "role": role, "permissions": perms})
    assert mk("ok1", "staff", ["students.view"]).status_code == 201          # within own permissions
    assert mk("no1", "staff", ["fees.manage"]).status_code == 403             # permission they lack
    assert mk("no2", "staff", ["users.manage"]).status_code == 403            # only admin grants this
    assert mk("no3", "admin", []).status_code == 403                          # cannot create an admin
    owner_id = next(u["id"] for u in client.get("/api/users", headers=mh).json() if u["username"] == "ownerA")
    assert client.put(f"/api/users/{owner_id}", headers=mh, json={"active": False}).status_code == 403
    assert client.post(f"/api/users/{owner_id}/reset-password", headers=mh).status_code == 403
    assert client.delete(f"/api/users/{owner_id}", headers=mh).status_code == 403


# ---------- student privacy ----------
def test_student_sees_only_own_details(client, world):
    h = login(client, "kid1")
    assert client.get(f"/api/students/{world['s1']}", headers=h).status_code == 200
    assert client.get(f"/api/students/{world['s2']}", headers=h).status_code == 403
    assert client.get(f"/api/students/{world['s2']}/fees", headers=h).status_code == 403


def test_student_own_fees_visible_but_not_others_in_list(client, world):
    h = login(client, "kid1")
    own = client.get(f"/api/students/{world['s1']}", headers=h).json()
    assert own["fees"]["pending"] == 30000
    rows = client.get("/api/students", headers=h).json()
    assert rows["detailed"] is False
    for row in rows["items"]:
        assert "fee_pending" not in row and "overall_pct" not in row and "phone" not in row


def test_student_cannot_modify_anything(client, world):
    h = login(client, "kid1")
    assert client.post("/api/subjects", headers=h, json={"name": "Art", "grade": "5"}).status_code == 403
    assert client.put(f"/api/students/{world['s1']}", headers=h, json={}).status_code in (403, 422)
    assert client.post(f"/api/students/{world['s1']}/marks", headers=h, json={"subject_id": world["sub_a"], "exam": "UT1", "academic_year": "2025-26", "score": 25}).status_code == 403
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.get("/api/dashboard", headers=h).status_code == 403


def test_student_can_see_staff_events_subjects(client, world):
    h = login(client, "kid1")
    assert client.get("/api/staff", headers=h).status_code == 200
    assert client.get("/api/events", headers=h).status_code == 200
    assert client.get("/api/subjects", headers=h).status_code == 200


def test_chatbot_respects_student_privacy(client, world):
    h = login(client, "kid1")
    other = client.post("/api/chat", headers=h, json={"question": "What are the marks of Bala Rao?"}).json()["answer"]
    assert "don't have access" in other
    fee = client.post("/api/chat", headers=h, json={"question": "Which students have pending fees?"}).json()["answer"]
    assert "don't have access" in fee
    mine = client.post("/api/chat", headers=h, json={"question": "How are my marks?"}).json()["answer"]
    assert "Asha Rao" in mine and "Bala" not in mine


def test_chatbot_scoped_to_school(client, world):
    h = login(client, "ownerB")
    ans = client.post("/api/chat", headers=h, json={"question": "What events are coming up?"}).json()["answer"]
    assert "Only A event" not in ans
    ans = client.post("/api/chat", headers=h, json={"question": "Tell me about Asha Rao"}).json()["answer"]
    assert "Asha" not in ans


# ---------- photos ----------
def test_student_photo_needs_approval(client, world):
    sh, oh = login(client, "kid1"), login(client, "ownerA")
    sid = world["s1"]
    assert client.post(f"/api/students/{sid}/photo-request", headers=sh, content=PNG).status_code == 204
    # not visible as the student's photo until approved
    assert client.get(f"/api/students/{sid}/photo", headers=oh).status_code == 404
    assert client.get("/api/photo-requests", headers=oh).json()[0]["student_id"] == sid
    # a student cannot approve their own request
    assert client.post(f"/api/students/{sid}/photo-request/approve", headers=sh).status_code == 403
    assert client.post(f"/api/students/{sid}/photo-request/approve", headers=oh).status_code == 204
    assert client.get(f"/api/students/{sid}/photo", headers=oh).status_code == 200
    assert client.get("/api/photo-requests", headers=oh).json() == []


def test_photo_reject_leaves_photo_unchanged(client, world):
    sh, oh = login(client, "kid1"), login(client, "ownerA")
    sid = world["s1"]
    client.post(f"/api/students/{sid}/photo-request", headers=sh, content=PNG)
    assert client.post(f"/api/students/{sid}/photo-request/reject", headers=oh).status_code == 204
    assert client.get(f"/api/students/{sid}/photo", headers=oh).status_code == 404


def test_student_cannot_request_for_someone_else_or_set_directly(client, world):
    sh = login(client, "kid1")
    assert client.post(f"/api/students/{world['s2']}/photo-request", headers=sh, content=PNG).status_code == 403
    assert client.post(f"/api/students/{world['s1']}/photo", headers=sh, content=PNG).status_code == 403


def test_upload_rejects_non_images_and_oversize(client, world):
    sh = login(client, "kid1")
    assert client.post(f"/api/students/{world['s1']}/photo-request", headers=sh, content=b"<script>alert(1)</script>").status_code == 415
    assert client.post(f"/api/students/{world['s1']}/photo-request", headers=sh, content=PNG + b"\x00" * (3 * 1024 * 1024)).status_code == 413


def test_staff_photo_permissions(client, world):
    oh, ph = login(client, "ownerA"), login(client, "plainA")
    staff_id = client.get("/api/staff", headers=oh).json()[0]["id"]
    assert client.post(f"/api/staff/{staff_id}/photo", headers=ph, content=PNG).status_code == 403
    assert client.post(f"/api/staff/{staff_id}/photo", headers=oh, content=PNG).status_code == 204
    assert client.get(f"/api/staff/{staff_id}/photo", headers=ph).status_code == 200


# ---------- subjects / chapters CRUD ----------
def test_subject_and_chapter_crud(client, world):
    h = login(client, "ownerA")
    sid = client.post("/api/subjects", headers=h, json={"name": "Art", "grade": "5"}).json()["id"]
    assert client.post("/api/subjects", headers=h, json={"name": "Art", "grade": "5"}).status_code == 409
    assert client.put(f"/api/subjects/{sid}", headers=h, json={"name": "Fine Art"}).json()["name"] == "Fine Art"
    cid = client.post(f"/api/subjects/{sid}/chapters", headers=h, json={"number": 1, "title": "Colours"}).json()["id"]
    assert client.put(f"/api/chapters/{cid}", headers=h, json={"number": 2, "title": "Shapes"}).status_code == 200
    assert client.get(f"/api/subjects/{sid}", headers=h).json()["chapters"][0]["title"] == "Shapes"
    assert client.delete(f"/api/chapters/{cid}", headers=h).status_code == 204
    assert client.delete(f"/api/subjects/{sid}", headers=h).status_code == 204


def test_staff_crud_and_detail(client, world):
    h = login(client, "ownerA")
    body = {"name": "New Teacher", "gender": "Female", "designation": "Teacher", "department": "Primary",
            "qualification": "M.Ed", "experience_years": 3, "subjects": "Maths", "phone": "9999999990",
            "email": "n@x.com", "joined_on": "2024-06-01"}
    sid = client.post("/api/staff", headers=h, json=body).json()["id"]
    assert client.put(f"/api/staff/{sid}", headers=h, json={**body, "designation": "Senior Teacher"}).json()["designation"] == "Senior Teacher"
    d = client.get(f"/api/staff/{sid}", headers=h).json()
    assert d["qualification"] == "M.Ed" and d["teaches"][0]["name"] == "Maths" and d["can"]["edit"] is True
    assert client.delete(f"/api/staff/{sid}", headers=h).status_code == 204


def test_staff_gets_generated_id_and_login_name(client, world):
    from datetime import date
    y, a = date.today().year, world["a"]
    h = login(client, "ownerA")
    body = {"employee_id": "HACK", "name": "New Teacher", "gender": "Female", "designation": "Teacher", "department": "Primary",
            "qualification": "M.Ed", "experience_years": 3, "phone": "9999999990", "email": "n@x.com", "joined_on": "2024-06-01"}
    t1 = client.post("/api/staff", headers=h, json=body)
    t2 = client.post("/api/staff", headers=h, json={**body, "name": "Second Teacher"})
    p = client.post("/api/staff", headers=h, json={**body, "name": "Head Person", "designation": "Principal"})
    # client-supplied employee_id is ignored; ids are school+year+letter+number
    assert t1.json()["employee_id"] == f"{a}{y}t001"
    assert t2.json()["employee_id"] == f"{a}{y}t002"
    assert p.json()["employee_id"] == f"{a}{y}p001"
    # the employee_id cannot be changed on update
    u = client.put(f"/api/staff/{t1.json()['id']}", headers=h, json={**body, "employee_id": "X1", "name": "Renamed"})
    assert u.json()["employee_id"] == f"{a}{y}t001"
    # a staff login linked to a profile uses the staff ID as login name
    r = client.post("/api/users", headers=h, json={"username": "ignored", "full_name": "New Teacher", "role": "staff",
                                                    "staff_id": t1.json()["id"], "permissions": ["students.view"]})
    assert r.status_code == 201 and r.json()["username"] == f"{a}{y}t001"
    login(client, f"{a}{y}t001", r.json()["temp_password"])


def test_staff_list_is_short_view(client, world):
    row = client.get("/api/staff", headers=login(client, "kid1")).json()[0]
    assert "phone" not in row and "email" not in row and "name" in row


# ---------- auth hygiene ----------
def test_login_lockout_and_no_user_enumeration(client, world):
    r1 = client.post("/api/auth/login", json={"username": "ownerA", "password": "bad"})
    r2 = client.post("/api/auth/login", json={"username": "nobody", "password": "bad"})
    assert r1.json() == r2.json() and r1.status_code == r2.status_code == 401
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "ownerA", "password": "bad"})
    assert client.post("/api/auth/login", json={"username": "ownerA", "password": PW}).status_code == 429


def test_deactivated_user_cannot_use_token(client, world):
    oh = login(client, "ownerA")
    kh = login(client, "kid1")
    uid = next(u["id"] for u in client.get("/api/users", headers=oh).json() if u["username"] == "kid1")
    assert client.put(f"/api/users/{uid}", headers=oh, json={"active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=kh).status_code == 401


def test_create_student_login_and_password_change(client, world):
    oh = login(client, "ownerA")
    # any username sent for a student is ignored: the login name is the student ID
    r = client.post("/api/users", headers=oh, json={"username": "kid2", "full_name": "Bala Rao", "role": "student", "student_id": world["s2"]})
    assert r.status_code == 201
    assert r.json()["username"] == "A2"
    kh = login(client, "A2", r.json()["temp_password"])
    assert client.post("/api/auth/password", headers=kh, json={"current_password": "wrong", "new_password": "NewPassw0rd!!"}).status_code == 400
    assert client.post("/api/auth/password", headers=kh, json={"current_password": r.json()["temp_password"], "new_password": "NewPassw0rd!!"}).status_code == 204
    login(client, "A2", "NewPassw0rd!!")
    # cannot link a student from another school
    bad = client.post("/api/users", headers=oh, json={"full_name": "Other Kid", "role": "student", "student_id": world["sb"]})
    assert bad.status_code == 422


def _new_student(grade="9", name="Ravi Teja"):
    return {"name": name, "gender": "Male", "dob": "2012-01-01", "grade": grade, "section": "A",
            "guardian_name": "Parent", "phone": "9999999999"}


def test_new_student_gets_id_and_login(client, world):
    from datetime import date
    oh = login(client, "ownerA")
    y, a = date.today().year, world["a"]
    r1 = client.post("/api/students", headers=oh, json=_new_student("9"))
    r2 = client.post("/api/students", headers=oh, json=_new_student("9", "Sita Devi"))
    assert r1.status_code == 201 and r2.status_code == 201
    # school id + year + 's' + 2-digit class + 3-digit roll; roll increments
    assert r1.json()["admission_no"] == f"{a}{y}s09001"
    assert r2.json()["admission_no"] == f"{a}{y}s09002"
    assert r1.json()["login"]["username"] == f"{a}{y}s09001"
    # the new student can sign in with ID + the one-time password, and sees only themself
    sh = login(client, f"{a}{y}s09001", r1.json()["login"]["temp_password"])
    assert client.get("/api/auth/me", headers=sh).json()["role"] == "student"
    assert client.get(f"/api/students/{r2.json()['id']}", headers=sh).status_code == 403
    # LKG / UKG / class 10 codes
    assert client.post("/api/students", headers=oh, json=_new_student("LKG")).json()["admission_no"] == f"{a}{y}s90001"
    assert client.post("/api/students", headers=oh, json=_new_student("UKG")).json()["admission_no"] == f"{a}{y}s91001"
    assert client.post("/api/students", headers=oh, json=_new_student("10")).json()["admission_no"] == f"{a}{y}s10001"


def test_student_id_is_unique_across_schools_and_not_editable(client, world):
    from datetime import date
    y = date.today().year
    a = client.post("/api/students", headers=login(client, "ownerA"), json=_new_student("5"))
    b = client.post("/api/students", headers=login(client, "ownerB"), json=_new_student("5", "B Kid"))
    # the school id prefix keeps the two schools' IDs (and login names) apart
    assert a.json()["admission_no"] == f"{world['a']}{y}s05001"
    assert b.json()["admission_no"] == f"{world['b']}{y}s05001"
    assert a.json()["admission_no"] != b.json()["admission_no"]
    # sending an admission_no on create or update is ignored
    oh = login(client, "ownerA")
    body = {**_new_student("5"), "admission_no": "HACK1"}
    c = client.post("/api/students", headers=oh, json=body)
    code = f"{world['a']}{y}s05002"
    assert c.json()["admission_no"] == code
    u = client.put(f"/api/students/{c.json()['id']}", headers=oh, json={**body, "name": "Renamed Kid"})
    assert u.json()["admission_no"] == code and u.json()["name"] == "Renamed Kid"


def test_no_auth_gets_401(client, world):
    for p in ("/api/students", "/api/staff", "/api/subjects", "/api/events", "/api/gallery", "/api/goals", "/api/school", "/api/dashboard"):
        assert client.get(p).status_code == 401, p


def test_fee_register_permission_and_scope(client, world):
    assert client.get("/api/fees", headers=login(client, "teacherA")).status_code == 403
    assert client.get("/api/fees", headers=login(client, "kid1")).status_code == 403
    d = client.get("/api/fees", headers=login(client, "ownerA")).json()
    assert {i["name"] for i in d["items"]} == {"Asha Rao", "Bala Rao"}
    assert d["summary"]["total"] == 80000 and d["summary"]["pending"] == 60000
    assert client.get("/api/fees?status=Paid", headers=login(client, "ownerA")).json()["items"] == []
    b = client.get("/api/fees", headers=login(client, "ownerB")).json()
    assert [i["name"] for i in b["items"]] == ["Other School Kid"] and b["summary"]["total"] == 0


# ---------- assistant: structured replies + persistent history ----------
def test_assistant_returns_stats_bars_and_buttons(client, world):
    h = login(client, "ownerA")
    r = client.post("/api/chat", headers=h, json={"question": "Tell me about Asha Rao"}).json()
    assert "Asha Rao" in r["answer"] and r["stats"] and r["bars"]
    labels = [a["label"] for a in r["actions"]]
    assert "Open profile" in labels and "Marks & performance" in labels
    assert all(a["to"].startswith("/") for a in r["actions"])  # in-app routes only
    assert any(a["to"].startswith("/messages?to=") for a in r["actions"])  # Asha has a login
    t = client.post("/api/chat", headers=h, json={"question": "Who are the top performers?"}).json()
    assert t["bars"] and any(a["to"].startswith("/students/") for a in t["actions"])


def test_assistant_history_persists_clears_and_is_private(client, world):
    oh, th = login(client, "ownerA"), login(client, "teacherA")
    client.post("/api/chat", headers=oh, json={"question": "How many students are in class 5?"})
    h = client.get("/api/chat/history", headers=oh).json()["messages"]
    assert [m["who"] for m in h] == ["me", "bot"] and h[1]["stats"]
    assert client.get("/api/chat/history", headers=th).json()["messages"] == []  # not shared
    assert client.delete("/api/chat/history", headers=th).status_code == 204
    assert len(client.get("/api/chat/history", headers=oh).json()["messages"]) == 2  # only my own cleared
    assert client.delete("/api/chat/history", headers=oh).status_code == 204
    assert client.get("/api/chat/history", headers=oh).json()["messages"] == []


def test_assistant_student_gets_no_message_button_for_students_or_fee_stats_of_others(client, world):
    h = login(client, "kid1")
    r = client.post("/api/chat", headers=h, json={"question": "How are my marks?"}).json()
    assert all(not a["to"].startswith("/messages") for a in r["actions"])
    assert r["actions"][0]["to"].startswith("/me")
    other = client.post("/api/chat", headers=h, json={"question": "fee of Bala Rao"}).json()
    assert "don't have access" in other["answer"] and not other["stats"] and not other["actions"]


# ---------- direct messages ----------
def _uid(client, h):
    return client.get("/api/auth/me", headers=h).json()["id"]


def test_direct_messages_flow_and_clear_is_per_side(client, world):
    oh, th = login(client, "ownerA"), login(client, "teacherA")
    tid = _uid(client, th)
    assert client.post(f"/api/messages/with/{tid}", headers=oh, json={"body": "Please share the Class 5 results"}).status_code == 201
    assert client.get("/api/messages/unread", headers=th).json()["count"] == 1
    th_threads = client.get("/api/messages/threads", headers=th).json()
    assert th_threads[0]["unread"] == 1 and th_threads[0]["name"] == "Owner A"
    oid = th_threads[0]["id"]
    conv = client.get(f"/api/messages/with/{oid}", headers=th).json()
    assert conv["messages"][0]["body"].startswith("Please share") and conv["messages"][0]["mine"] is False
    assert client.get("/api/messages/unread", headers=th).json()["count"] == 0  # opening marks read
    client.post(f"/api/messages/with/{oid}", headers=th, json={"body": "Sure, sending now"})
    # teacher clears: owner still sees everything, teacher sees nothing
    assert client.delete(f"/api/messages/with/{oid}", headers=th).status_code == 204
    assert client.get(f"/api/messages/with/{oid}", headers=th).json()["messages"] == []
    assert len(client.get(f"/api/messages/with/{tid}", headers=oh).json()["messages"]) == 2
    # a new message after clearing shows up again for the teacher
    client.post(f"/api/messages/with/{tid}", headers=oh, json={"body": "Thanks"})
    assert [m["body"] for m in client.get(f"/api/messages/with/{oid}", headers=th).json()["messages"]] == ["Thanks"]


def test_direct_message_rules(client, world):
    oh, kh, th = login(client, "ownerA"), login(client, "kid1"), login(client, "teacherA")
    bh = login(client, "ownerB")
    tid, oid, bid, kid = _uid(client, th), _uid(client, oh), _uid(client, bh), _uid(client, kh)
    # students can write to staff and the owner, not to other students or themselves
    assert client.post(f"/api/messages/with/{tid}", headers=kh, json={"body": "Sir, a doubt"}).status_code == 201
    assert client.post(f"/api/messages/with/{oid}", headers=kh, json={"body": "Hello"}).status_code == 201
    assert client.post(f"/api/messages/with/{kid}", headers=kh, json={"body": "me"}).status_code == 404
    names = {c["name"] for c in client.get("/api/messages/contacts", headers=kh).json()}
    assert "Teacher A" in names and "Asha Rao" not in names
    # staff can write to a student
    assert client.post(f"/api/messages/with/{kid}", headers=th, json={"body": "Come see me"}).status_code == 201
    # never across schools, never to the superadmin, never to a missing user
    assert client.post(f"/api/messages/with/{bid}", headers=oh, json={"body": "x"}).status_code == 404
    assert client.get(f"/api/messages/with/{bid}", headers=oh).status_code == 404
    assert client.post("/api/messages/with/99999", headers=oh, json={"body": "x"}).status_code == 404
    # validation
    assert client.post(f"/api/messages/with/{tid}", headers=oh, json={"body": "   "}).status_code == 422
    assert client.post(f"/api/messages/with/{tid}", headers=oh, json={"body": "a" * 1001}).status_code == 422
    # a third person cannot read someone else's conversation
    assert all(m["body"] != "Sir, a doubt" for m in client.get(f"/api/messages/with/{kid}", headers=oh).json()["messages"])
    # unauthenticated
    assert client.get("/api/messages/threads").status_code == 401
    # message text is stored and returned as plain text (the UI renders it escaped)
    client.post(f"/api/messages/with/{tid}", headers=oh, json={"body": "<script>alert(1)</script>"})
    assert client.get(f"/api/messages/with/{oid}", headers=th).json()["messages"][-1]["body"] == "<script>alert(1)</script>"


# ---------- superadmin console ----------
def test_platform_routes_are_superadmin_only(client, world):
    paths = ["/api/platform/overview", f"/api/schools/{world['a']}", f"/api/schools/{world['a']}/branches", "/api/audit"]
    for u in ("ownerA", "teacherA", "kid1"):
        h = login(client, u)
        for p in paths:
            assert client.get(p, headers=h).status_code == 403, (u, p)
        assert client.put(f"/api/schools/{world['a']}", headers=h, json={"name": "Hacked"}).status_code == 403
        assert client.post(f"/api/schools/{world['a']}/branches", headers=h, json={"name": "Evil"}).status_code == 403
    assert client.get("/api/audit").status_code == 401


def test_overview_and_school_detail(client, world):
    h = login(client, "super")
    o = client.get("/api/platform/overview", headers=h).json()
    assert o["totals"]["schools"] == 2 and o["totals"]["students"] == 3
    row = next(r for r in o["schools"] if r["id"] == world["a"])
    assert row["students"] == 2 and row["fee_total"] == 80000 and row["fee_paid"] == 20000 and row["collection_pct"] == 25
    assert len(o["growth"]) == 12 and sum(g["students"] for g in o["grades"]) == 3
    d = client.get(f"/api/schools/{world['a']}", headers=h).json()
    assert d["counts"]["students"] == 2 and d["counts"]["staff"] == 1 and d["fees"]["pending"] == 60000
    assert d["owner"]["username"] == "ownerA" and d["usage"]["students"]["max"] == 1000
    assert {p["username"] for p in d["people"]} >= {"ownerA", "teacherA"}
    assert client.get("/api/schools/9999", headers=h).status_code == 404


def test_superadmin_edits_school_details_and_audit_logged(client, world):
    h = login(client, "super")
    body = {"name": "School A Renamed", "city": "Pune", "board": "ICSE", "plan": "Premium", "max_students": 5,
            "max_staff": 7, "subscription_end": "2030-01-01", "website": "https://a.example", "email": "a@a.example"}
    r = client.put(f"/api/schools/{world['a']}", headers=h, json=body)
    assert r.status_code == 200 and r.json()["city"] == "Pune" and r.json()["plan"] == "Premium"
    assert r.json()["subscription_status"] == "Active"
    assert client.put(f"/api/schools/{world['a']}", headers=h, json={**body, "plan": "Gold"}).status_code == 422
    assert client.put(f"/api/schools/{world['a']}", headers=h, json={**body, "website": "javascript:alert(1)"}).status_code == 422
    # an empty form keeps the plan and limits
    r = client.put(f"/api/schools/{world['a']}", headers=h, json={"name": "School A Renamed"})
    assert r.json()["plan"] == "Premium" and r.json()["max_students"] == 5 and r.json()["city"] is None
    log_rows = client.get(f"/api/audit?school_id={world['a']}", headers=h).json()
    assert any(a["action"] == "school_updated" and "plan" in a["detail"] for a in log_rows)


def test_plan_limits_block_new_students_and_staff(client, world):
    sh = login(client, "super")
    client.put(f"/api/schools/{world['a']}", headers=sh, json={"name": "School A", "max_students": 2, "max_staff": 1})
    oh = login(client, "ownerA")
    r = client.post("/api/students", headers=oh, json=_new_student("5"))
    assert r.status_code == 403 and "plan" in r.json()["detail"]
    body = {"name": "Extra Teacher", "gender": "Female", "designation": "Teacher", "department": "Primary", "qualification": "B.Ed",
            "experience_years": 1, "phone": "9999999990", "email": "n@x.com", "joined_on": "2024-06-01"}
    assert client.post("/api/staff", headers=oh, json=body).status_code == 403
    client.put(f"/api/schools/{world['a']}", headers=sh, json={"name": "School A", "max_students": 10, "max_staff": 10})
    assert client.post("/api/students", headers=oh, json=_new_student("5")).status_code == 201


def test_branches_crud_and_main_rules(client, world):
    h = login(client, "super")
    a = world["a"]
    b1 = client.post(f"/api/schools/{a}/branches", headers=h, json={"name": "North Campus", "city": "Delhi"}).json()
    assert b1["is_main"] is True  # the first branch becomes the main one
    b2 = client.post(f"/api/schools/{a}/branches", headers=h, json={"name": "South Campus", "phone": "9999999990"}).json()
    assert b2["is_main"] is False
    assert client.delete(f"/api/schools/{a}/branches/{b1['id']}", headers=h).status_code == 422
    assert client.put(f"/api/schools/{a}/branches/{b2['id']}/state", headers=h, json={"is_main": True}).json()["is_main"] is True
    names = {x["name"]: x for x in client.get(f"/api/schools/{a}/branches", headers=h).json()}
    assert names["North Campus"]["is_main"] is False
    assert client.put(f"/api/schools/{a}/branches/{b2['id']}/state", headers=h, json={"active": False}).status_code == 422
    assert client.put(f"/api/schools/{a}/branches/{b1['id']}", headers=h, json={"name": "North Renamed"}).json()["name"] == "North Renamed"
    assert client.delete(f"/api/schools/{a}/branches/{b1['id']}", headers=h).status_code == 204
    # a branch cannot be reached through another school's id
    assert client.put(f"/api/schools/{world['b']}/branches/{b2['id']}", headers=h, json={"name": "Stolen"}).status_code == 404


def test_new_school_gets_main_branch_and_details(client, world):
    h = login(client, "super")
    r = client.post("/api/schools", headers=h, json={"name": "Detail School", "owner_name": "Own Er", "city": "Goa",
                                                      "plan": "Free", "max_students": 50})
    sid = r.json()["school"]["id"]
    d = client.get(f"/api/schools/{sid}", headers=h).json()
    assert d["city"] == "Goa" and d["plan"] == "Free" and d["max_students"] == 50
    assert [b["name"] for b in d["branches"]] == ["Main Campus"] and d["branches"][0]["is_main"] is True


def test_superadmin_user_controls_scoped_to_school(client, world):
    h = login(client, "super")
    a = world["a"]
    d = client.get(f"/api/schools/{a}", headers=h).json()
    teacher = next(p for p in d["people"] if p["username"] == "teacherA")
    r = client.put(f"/api/schools/{a}/users/{teacher['id']}/active", headers=h, json={"active": False})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"username": "teacherA", "password": PW}).status_code == 401
    r = client.post(f"/api/schools/{a}/users/{teacher['id']}/reset-password", headers=h)
    assert r.status_code == 200 and r.json()["username"] == "teacherA" and r.json()["temp_password"]
    # a user of another school (or the superadmin) cannot be reached through this school's route
    assert client.put(f"/api/schools/{world['b']}/users/{teacher['id']}/active", headers=h, json={"active": False}).status_code == 404
    me_id = client.get("/api/auth/me", headers=h).json()["id"]
    assert client.put(f"/api/schools/{a}/users/{me_id}/active", headers=h, json={"active": False}).status_code == 404
    acts = [x["action"] for x in client.get(f"/api/audit?school_id={a}", headers=h).json()]
    assert "user_disabled" in acts and "user_password_reset" in acts
    assert all("temp_password" not in str(x) for x in client.get("/api/audit", headers=h).json())


def test_login_records_last_login_and_school_delete_keeps_audit(client, world):
    h = login(client, "super")
    login(client, "ownerA")
    d = client.get(f"/api/schools/{world['a']}", headers=h).json()
    assert d["owner"]["last_login"] and d["active_users_7d"] >= 1
    assert client.delete(f"/api/schools/{world['b']}", headers=h).status_code == 204
    assert any(a["action"] == "school_deleted" and a["school_name"] == "School B" for a in client.get("/api/audit", headers=h).json())
