# School Management Suite (multi-school)

React (Vite) frontend + Python (FastAPI) backend with a grounded AI assistant.
One platform, many schools: every school's data is fully isolated.

## Run it

Requires Python 3.13 (3.9 is end-of-life) and Node 20+.

```bash
# 1. Backend  (http://127.0.0.1:8000, API docs at /docs)
cd backend
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m app.seed --reset   # demo data; generates passwords into backend/.env
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Frontend (http://127.0.0.1:5173)
cd frontend
npm install
npm run dev
```

Tests: `cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q tests`

## Demo logins

Passwords are generated into `backend/.env` (git-ignored). Run `grep PASSWORD backend/.env`.

| Username | Role | What it shows |
|---|---|---|
| `superadmin` | Platform owner | Create/disable/delete schools, hand each owner a login |
| `admin` | School owner (Sunrise Public School) | Everything in that school, plus users and permissions |
| `teacher` | Staff | View students, enter marks only (granted permissions) |
| `202605001` (any student ID) | Student | Own profile, marks, fees; subjects, staff, events, gallery; never other students' data. All demo students share `STUDENT_PASSWORD` |
| `owner2` | School owner (Greenfield Academy) | A brand-new, empty school |

## Student IDs and logins

Every student gets a 9-digit ID generated as **year + 2-digit class + 3-digit roll number**, e.g.
`202609011` = 2026, class 9, roll 011 (LKG = `90`, UKG = `91`, class 10 = `10`). The ID is the
student's login name. Adding a student in the app creates the ID and the login together and shows
the one-time temporary password once; share it with the student or parent. The ID never changes, and
IDs are unique across the whole platform, so two schools can never share a login name.

## Roles and permissions

- **superadmin** has no school. Creates a school plus its owner (a temporary password is shown once).
- **admin** (school owner) holds every permission and manages users.
- **staff** get only the permissions an admin ticks: `students.view`, `students.manage`, `marks.edit`,
  `fees.view`, `fees.manage`, `staff.manage`, `subjects.manage`, `content.manage`, `school.manage`,
  `photos.approve`, `users.manage` (admin-only to grant). Nobody can grant a permission they lack.
- **student** sees only their own record. Their new profile photo waits for approval before it shows.

Edit controls (add / edit / delete) appear only where the user holds the matching permission.

## What is built

| Area | Features |
|---|---|
| Dashboard | Clickable tiles for every area, KPIs, class-wise averages, score distribution, pending fees, top / at-risk lists |
| Subjects | LKG to Class 10; add / rename / delete subjects; **chapters** per subject with add / edit / delete |
| Students | Add / search / filter by class and section; full profile with year dropdown, per-test bar charts, progress, strengths radar, weak-subject insights, fee summary |
| Fees | Register by class and status, payments, per-student pending |
| Staff | Short card with Quick view, **separate full page per member**, photo upload, edit / delete |
| Events, Gallery, Goals | Full CRUD, gallery image upload (validated PNG/JPEG/WebP, max 3 MB) |
| About | Per-school profile, editable by owners |
| Users & Access | Create logins, tick permissions, reset passwords, disable |
| Photo approvals | Approve / reject student photo changes |
| Assistant | Floating chat with stat cards, performance bars and action buttons (open profile, marks, fees, message the person). History is saved per user until they clear it |
| Messages | Private person-to-person chat inside a school (owner, staff, students). Unread badge, history kept until cleared (clearing only affects your own view) |

## Messaging rules

Owners and staff can message anyone in their school. Students can message staff and the owner, never
other students. Nothing crosses schools. Clearing a chat hides it for you only; the other person keeps
their copy. Message text is stored as plain text and rendered escaped.

## Chatbot design

Answers come from database queries only (no model-generated SQL), so it cannot invent data or
leak beyond what the logged-in user may see (a student asking about another student or about
fees gets a refusal). Optionally set `LLM_BASE_URL` (https only), `LLM_API_KEY`, `LLM_MODEL` in
`backend/.env` to have an OpenAI-compatible model rephrase the facts; if unset or failing it
falls back to the grounded answer.

## Security notes

- Passwords hashed with bcrypt; JWT sessions (60 min); 5 failed logins lock a username for 15 min
- Multi-tenant: every query is filtered by `school_id`; cross-school access returns 404
- RBAC checked on every request server-side; the UI only hides buttons as a convenience
- Inputs validated server-side (Pydantic); ORM only, no raw SQL
- Photos are served only through authenticated endpoints, validated by magic bytes, max 3 MB
- Servers bind to 127.0.0.1; CORS restricted; generic 500 errors, details only in server logs
- Secrets only in `.env` (git-ignored). Front-end token lives in sessionStorage

See [`PLAN.md`](PLAN.md) for the roadmap to production.
