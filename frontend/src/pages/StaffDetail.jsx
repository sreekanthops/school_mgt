import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CalendarRange, ClipboardList, Mail, Pencil, Phone, Star, Trash2, X } from "lucide-react";
import { api, GRADES } from "../api.js";
import { useAuth } from "../auth.jsx";
import { SECTIONS, staffFields } from "../forms.js";
import { Async, Badge, Confirm, FormModal, Modal, Photo, PhotoUpload, useLoad } from "../components/ui.jsx";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const LEAVE_TYPES = ["Casual", "Sick", "Earned", "Maternity", "Paternity", "Unpaid", "Other"];
const STATUS_KIND = { pending: "warn", approved: "good", rejected: "bad" };

function ScheduleTab({ schedule }) {
  if (!schedule || schedule.length === 0) {
    return <div className="muted">No timetable slots assigned to this staff member yet.</div>;
  }
  // Group by day
  const byDay = {};
  for (const p of schedule) {
    if (!byDay[p.day_of_week]) byDay[p.day_of_week] = [];
    byDay[p.day_of_week].push(p);
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {DAYS.filter((d) => byDay[d]).map((day) => (
        <div key={day}>
          <div style={{ fontWeight: 600, color: "var(--primary)", marginBottom: 6 }}>{day}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {byDay[day].map((p) => (
              <div key={p.id} className="card" style={{ padding: "8px 12px", minWidth: 160, flex: "1 1 160px" }}>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  {p.start_time && p.end_time ? `${p.start_time} – ${p.end_time}` : `Period ${p.period_number}`}
                </div>
                <div style={{ fontWeight: 600, marginTop: 2 }}>
                  {p.subject ? (
                    <Link to={`/subjects/${p.subject.id}`} style={{ color: "var(--primary)" }}>
                      {p.subject.name}
                    </Link>
                  ) : p.label || "–"}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  Class {p.grade}-{p.section}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function LeaveApplyModal({ staffId, onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ from_date: today, to_date: today, leave_type: "Casual", reason: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/leaves", { method: "POST", body: f });
      onDone();
      onClose();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Apply for Leave" onClose={onClose}>
      <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          <div className="field">
            <label>From date *</label>
            <input type="date" required value={f.from_date}
              onChange={(e) => setF({ ...f, from_date: e.target.value })} />
          </div>
          <div className="field">
            <label>To date *</label>
            <input type="date" required value={f.to_date} min={f.from_date}
              onChange={(e) => setF({ ...f, to_date: e.target.value })} />
          </div>
          <div className="field">
            <label>Leave type *</label>
            <select value={f.leave_type} onChange={(e) => setF({ ...f, leave_type: e.target.value })}>
              {LEAVE_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Reason</label>
          <textarea rows={3} maxLength={500} value={f.reason}
            onChange={(e) => setF({ ...f, reason: e.target.value })}
            placeholder="Optional — describe the reason for leave" />
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Submitting…" : "Submit application"}</button>
        </div>
      </form>
    </Modal>
  );
}

function LeavesTab({ staffId, canManage, isOwnProfile }) {
  const { session } = useAuth();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api(`/leaves?staff_id=${staffId}`), [tick, staffId]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(leaves) => (
        <>
          <div className="row" style={{ marginBottom: 14, justifyContent: "flex-end" }}>
            {isOwnProfile && (
              <button className="btn sm" onClick={() => setDlg("apply")}>
                <ClipboardList size={14} /> Apply for leave
              </button>
            )}
          </div>
          {leaves.length === 0 && <div className="muted">No leave applications found.</div>}
          {leaves.map((l) => (
            <div key={l.id} className="card" style={{ marginBottom: 10, padding: "12px 16px" }}>
              <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}>
                <div>
                  <b>{l.leave_type}</b>
                  <span className="muted" style={{ marginLeft: 8 }}>
                    {l.from_date} – {l.to_date}
                    {l.days > 1 ? ` (${l.days} days)` : " (1 day)"}
                  </span>
                </div>
                <Badge kind={STATUS_KIND[l.status]}>{l.status}</Badge>
              </div>
              {l.reviewer_name && l.status === "pending" && (
                <div className="small muted" style={{ marginTop: 4 }}>
                  Reviewer: {l.reviewer_name}
                </div>
              )}
              {l.reason && <div className="small muted" style={{ marginTop: 4 }}>{l.reason}</div>}
              {l.review_note && (
                <div className="small" style={{ marginTop: 4, color: l.status === "rejected" ? "var(--bad,#e11d48)" : "var(--good,#16a34a)" }}>
                  Note: {l.review_note}
                </div>
              )}
              <div className="row" style={{ marginTop: 6, gap: 8, justifyContent: "flex-end" }}>
                {l.status === "pending" && (isOwnProfile || canManage) && (
                  <button className="btn ghost sm danger" onClick={async () => {
                    await api(`/leaves/${l.id}`, { method: "DELETE" });
                    reload();
                  }}>Cancel</button>
                )}
                {l.status === "pending" && canManage && (
                  <>
                    <button className="btn sm" style={{ background: "var(--good,#16a34a)", color: "#fff" }}
                      onClick={() => setDlg({ type: "review", lid: l.id, action: "approved" })}>
                      Approve
                    </button>
                    <button className="btn danger sm"
                      onClick={() => setDlg({ type: "review", lid: l.id, action: "rejected" })}>
                      Reject
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
          {dlg === "apply" && (
            <LeaveApplyModal staffId={staffId} onClose={() => setDlg(null)} onDone={reload} />
          )}
          {dlg?.type === "review" && (
            <ReviewModal lid={dlg.lid} action={dlg.action} onClose={() => setDlg(null)} onDone={reload} />
          )}
        </>
      )}
    </Async>
  );
}

function ReviewModal({ lid, action, onClose, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api(`/leaves/${lid}/review`, { method: "PUT", body: { status: action, review_note: note || null } });
      onDone();
      onClose();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={action === "approved" ? "Approve leave" : "Reject leave"} onClose={onClose}>
      <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
        {err && <div className="error">{err}</div>}
        <div className="field">
          <label>Note (optional)</label>
          <textarea rows={3} maxLength={300} value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note to the staff member (optional)" />
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>
            {busy ? "Saving…" : action === "approved" ? "✅ Approve" : "❌ Reject"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ── Class Head card ───────────────────────────────────────────────────────────
function ClassHeadCard({ staffId, classTeacherOf, onDone }) {
  const [assigning, setAssigning] = useState(false);
  const [grade, setGrade] = useState(GRADES[0]);
  const [section, setSection] = useState(SECTIONS[0]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function assign(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api(`/staff/${staffId}/class-head`, { method: "PUT", body: { grade, section } });
      setAssigning(false);
      onDone();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api(`/staff/${staffId}/class-head`, { method: "DELETE" });
      onDone();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}><Star size={15} style={{ verticalAlign: -2, marginRight: 4 }} />Class Head</h3>
        {classTeacherOf
          ? <button className="btn ghost sm danger" disabled={busy} onClick={remove}><X size={13} /> Remove</button>
          : <button className="btn sm" onClick={() => setAssigning(true)}><Star size={13} /> Assign</button>}
      </div>
      {classTeacherOf
        ? <div><span className="chip">Section {classTeacherOf}</span><div className="small muted" style={{ marginTop: 6 }}>This staff member is the class head for section {classTeacherOf}. Student leave requests from this class are routed to them.</div></div>
        : <div className="muted small">Not assigned as class head for any section.</div>}
      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
      {assigning && (
        <form onSubmit={assign} style={{ marginTop: 12 }}>
          <div className="form-grid">
            <div className="field">
              <label>Grade</label>
              <select value={grade} onChange={(e) => setGrade(e.target.value)}>
                {GRADES.map((g) => <option key={g} value={g}>{g === "LKG" || g === "UKG" ? g : `Class ${g}`}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Section</label>
              <select value={section} onChange={(e) => setSection(e.target.value)}>
                {SECTIONS.map((s) => <option key={s} value={s}>Section {s}</option>)}
              </select>
            </div>
          </div>
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            <button className="btn" disabled={busy}>{busy ? "Saving…" : "Assign"}</button>
            <button type="button" className="btn ghost" onClick={() => setAssigning(false)}>Cancel</button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function StaffDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { session, can } = useAuth();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const [tab, setTab] = useState("details");
  const state = useLoad(() => api(`/staff/${id}`), [id, tick]);
  const reload = () => setTick((t) => t + 1);
  const canManageLeaves = session?.role === "admin" || can("leaves.manage");

  return (
    <Async state={state}>
      {(s) => {
        const isOwnProfile = session?.staff_id === s.id;
        return (
          <>
            <Link to="/staff" className="backlink"><ArrowLeft size={14} /> Staff</Link>
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="hero-cover" />
              <div className="hero">
                <Photo kind="staff" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} size={110} />
                <div style={{ flex: 1, minWidth: 220, paddingTop: 10 }}>
                  <h1 style={{ margin: 0 }}>{s.name}</h1>
                  <div className="muted">{s.designation} · {s.department}</div>
                  <div className="chip-list" style={{ marginTop: 8 }}>
                    {s.class_teacher_of && <span className="chip">Class teacher {s.class_teacher_of}</span>}
                    <span className="chip">{s.experience_years} yrs experience</span>
                  </div>
                </div>
                <div className="actions">
                  {s.can.photo && <PhotoUpload path={`/staff/${s.id}/photo`} onDone={reload} />}
                  {s.can.edit && <button className="btn ghost sm" onClick={() => setDlg("edit")}><Pencil size={14} /> Edit</button>}
                  {s.can.edit && <button className="btn danger sm" onClick={() => setDlg("del")}><Trash2 size={14} /> Delete</button>}
                </div>
              </div>
            </div>

            {/* ── Tabs ──────────────────────────────────────────────────── */}
            <div className="tabs">
              <button className={tab === "details" ? "on" : ""} onClick={() => setTab("details")}>Details</button>
              <button className={tab === "schedule" ? "on" : ""} onClick={() => setTab("schedule")}>
                <CalendarRange size={13} style={{ verticalAlign: -2, marginRight: 4 }} />Schedule
              </button>
              {(isOwnProfile || canManageLeaves) && (
                <button className={tab === "leaves" ? "on" : ""} onClick={() => setTab("leaves")}>
                  <ClipboardList size={13} style={{ verticalAlign: -2, marginRight: 4 }} />Leaves
                </button>
              )}
            </div>

            {/* ── Tab: Details ──────────────────────────────────────────── */}
            {tab === "details" && (
              <div className="grid g2">
                <div className="card">
                  <h3 style={{ marginTop: 0 }}>Details</h3>
                  <dl className="kv">
                    <dt>Staff ID</dt><dd>{s.employee_id}</dd>
                    <dt>Gender</dt><dd>{s.gender}</dd>
                    <dt>Qualification</dt><dd>{s.qualification}</dd>
                    <dt>Joined</dt><dd>{s.joined_on}</dd>
                    <dt>Phone</dt><dd><Phone size={13} /> {s.phone}</dd>
                    <dt>Email</dt><dd><Mail size={13} /> {s.email}</dd>
                  </dl>
                </div>
                <div className="card">
                  <h3 style={{ marginTop: 0 }}>Teaching</h3>
                  {s.teaches.length === 0 && <div className="muted">{s.subjects || "No subjects assigned."}</div>}
                  <div className="chip-list">
                    {s.teaches.map((t) => (
                      <Link key={t.id} to={`/subjects/${t.id}`} className="chip">{t.name} · {t.grade}</Link>
                    ))}
                  </div>
                  {s.bio && (<><h3>About</h3><p className="muted">{s.bio}</p></>)}
                </div>
                {s.can.edit && (
                  <ClassHeadCard staffId={s.id} classTeacherOf={s.class_teacher_of} onDone={reload} />
                )}
              </div>
            )}

            {/* ── Tab: Schedule ─────────────────────────────────────────── */}
            {tab === "schedule" && (
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
                  <h3 style={{ margin: 0 }}>Weekly Schedule</h3>
                  <Link to="/classes" className="btn ghost sm">Edit timetable</Link>
                </div>
                <ScheduleTab schedule={s.schedule} />
              </div>
            )}

            {/* ── Tab: Leaves ───────────────────────────────────────────── */}
            {tab === "leaves" && (isOwnProfile || canManageLeaves) && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Leave Applications</h3>
                <LeavesTab staffId={s.id} canManage={canManageLeaves} isOwnProfile={isOwnProfile} />
              </div>
            )}

            {dlg === "edit" && (
              <FormModal title="Edit staff member" fields={staffFields} initial={s} onClose={() => setDlg(null)}
                onSubmit={async (b) => { await api(`/staff/${s.id}`, { method: "PUT", body: b }); reload(); }} />
            )}
            {dlg === "del" && (
              <Confirm title="Delete staff member" message={`Delete ${s.name}? Linked logins will lose their staff link.`}
                onClose={() => setDlg(null)} onConfirm={async () => { await api(`/staff/${s.id}`, { method: "DELETE" }); nav("/staff"); }} />
            )}
          </>
        );
      }}
    </Async>
  );
}
