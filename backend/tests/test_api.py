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
    h = login(client, "super")
    r = client.post("/api/schools", headers=h, json={"name": "New Kids School", "owner_name": "New Owner", "owner_username": "newowner"})
    assert r.status_code == 201
    temp = r.json()["owner"]["temp_password"]
    oh = login(client, "newowner", temp)
    assert client.get("/api/school", headers=oh).json()["name"] == "New Kids School"
    assert client.get("/api/dashboard", headers=oh).json()["counts"]["students"] == 0
    # owner can now rename their own school
    assert client.put("/api/school", headers=oh, json={"name": "Renamed School"}).json()["name"] == "Renamed School"


def test_superadmin_endpoints_forbidden_to_others(client, world):
    for u in ("ownerA", "teacherA", "kid1"):
        h = login(client, u)
        assert client.get("/api/schools", headers=h).status_code == 403
        assert client.post("/api/schools", headers=h, json={"name": "x", "owner_name": "yy", "owner_username": "zzz"}).status_code == 403


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
    body = {"employee_id": "E9", "name": "New Teacher", "gender": "Female", "designation": "Teacher", "department": "Primary",
            "qualification": "M.Ed", "experience_years": 3, "subjects": "Maths", "phone": "9999999990",
            "email": "n@x.com", "joined_on": "2024-06-01"}
    sid = client.post("/api/staff", headers=h, json=body).json()["id"]
    assert client.put(f"/api/staff/{sid}", headers=h, json={**body, "designation": "Senior Teacher"}).json()["designation"] == "Senior Teacher"
    d = client.get(f"/api/staff/{sid}", headers=h).json()
    assert d["qualification"] == "M.Ed" and d["teaches"][0]["name"] == "Maths" and d["can"]["edit"] is True
    assert client.delete(f"/api/staff/{sid}", headers=h).status_code == 204


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
    r = client.post("/api/users", headers=oh, json={"username": "kid2", "full_name": "Bala Rao", "role": "student", "student_id": world["s2"]})
    assert r.status_code == 201
    kh = login(client, "kid2", r.json()["temp_password"])
    assert client.post("/api/auth/password", headers=kh, json={"current_password": "wrong", "new_password": "NewPassw0rd!!"}).status_code == 400
    assert client.post("/api/auth/password", headers=kh, json={"current_password": r.json()["temp_password"], "new_password": "NewPassw0rd!!"}).status_code == 204
    login(client, "kid2", "NewPassw0rd!!")
    # cannot link a student from another school
    bad = client.post("/api/users", headers=oh, json={"username": "kid3", "full_name": "Other Kid", "role": "student", "student_id": world["sb"]})
    assert bad.status_code == 422


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
