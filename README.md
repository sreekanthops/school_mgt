# Sunrise School Management Suite

React (Vite) frontend + Python (FastAPI) backend with a grounded AI assistant.

## Run it

Requires Python 3.13 (3.9 is end-of-life) and Node 20+.

```bash
# 1. Backend  (http://127.0.0.1:8000, API docs at /docs)
cd backend
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env              # already done if you ran the seed once
.venv/bin/python -m app.seed --reset   # demo data; generates passwords into backend/.env
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Frontend (http://127.0.0.1:5173)
cd frontend
npm install
npm run dev
```

Logins: `admin` (full access) and `teacher` (read + enter marks). Passwords are generated
into `backend/.env` (git-ignored) — open that file to read them.

## What is built

| Area | Features |
|---|---|
| Subjects | LKG to Class 10, subjects per class, teachers per subject |
| Students | Add/search/filter by class and section, list with overall % and fee status |
| Student detail | Profile, **year dropdown (current by default, previous years selectable)**, per-test bar charts (UT1, Midterm, UT2, Final), progress line, strength radar, weak-subject insights, all-marks table, rank, year-wise history |
| Fees | Total / paid / pending, payment history, record payments (admin) |
| Staff | Directory with search, class teacher, subjects, qualifications, contact |
| Events & Gallery | Upcoming/past events, filterable gallery |
| Future goals | Progress-tracked roadmap |
| About | Mission, vision, contact |
| Dashboard | KPIs, class-wise averages, score distribution, pending fees by class, top / at-risk / dues lists |
| Chatbot | Floating assistant answering from live database facts |

## Chatbot design

Answers are produced from database queries only (no model-generated SQL), so it cannot invent
data or leak beyond what the logged-in user can see. Optionally set `LLM_BASE_URL` (https only),
`LLM_API_KEY`, `LLM_MODEL` in `backend/.env` to have an OpenAI-compatible model rephrase the
facts more naturally; if unset or failing it falls back to the grounded answer.

## Security notes

- Passwords hashed with bcrypt; JWT sessions (60 min); 5 failed logins lock a username for 15 min
- Role-based access: write operations on students, fees, staff are admin-only
- All inputs validated server-side (Pydantic); ORM only, no raw SQL
- Servers bind to 127.0.0.1; CORS restricted; generic 500 errors, details only in server logs
- Secrets only in `.env` (git-ignored). Front-end token lives in sessionStorage

See [`PLAN.md`](PLAN.md) for the roadmap to production.
