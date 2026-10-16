import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle, ClipboardList, Plus, Search, XCircle } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, Modal, PageHead, useLoad } from "../components/ui.jsx";

const STATUS_KIND = { pending: "warn", approved: "good", rejected: "bad" };
const STAFF_LEAVE_TYPES = ["Casual", "Sick", "Earned", "Maternity", "Paternity", "Unpaid", "Other"];
const STUDENT_LEAVE_TYPES = ["Casual", "Sick", "Family", "Personal", "Other"];

// ── apply-leave modal ─────────────────────────────────────────────────────────
function ApplyLeaveModal({ isStudent, onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10);
  const types = isStudent ? STUDENT_LEAVE_TYPES : STAFF_LEAVE_TYPES;
  const [f, setF] = useState({ from_date: today, to_date: today, leave_type: types[0], reason: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

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
            <input type="date" required value={f.from_date} onChange={(e) => set("from_date", e.target.value)} />
          </div>
          <div className="field">
            <label>To date *</label>
            <input type="date" required value={f.to_date} min={f.from_date} onChange={(e) => set("to_date", e.target.value)} />
          </div>
          <div className="field">
            <label>Leave type *</label>
            <select value={f.leave_type} onChange={(e) => set("leave_type", e.target.value)}>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Reason (optional)</label>
          <textarea rows={3} maxLength={500} value={f.reason}
            onChange={(e) => set("reason", e.target.value)}
            placeholder="Briefly describe the reason…" />
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Submitting…" : "Submit application"}</button>
        </div>
      </form>
    </Modal>
  );
}

// ── review modal ──────────────────────────────────────────────────────────────
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
            placeholder="Add a note (optional)" />
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

// ── leave card ────────────────────────────────────────────────────────────────
function LeaveCard({ l, canManage, onApprove, onReject, onCancel }) {
  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}>
        <div>
          {l.applicant_name && (
            <Link
              to={l.kind === "student" ? `/students/${l.student_id}` : `/staff/${l.staff_id}`}
              style={{ fontWeight: 700 }}>
              {l.applicant_name}
            </Link>
          )}
          {l.kind === "student" && (
            <span className="chip" style={{ marginLeft: 6, fontSize: 11 }}>Student</span>
          )}
          <div className="small muted" style={{ marginTop: 2 }}>Applied: {l.applied_at?.slice(0, 10)}</div>
        </div>
        <Badge kind={STATUS_KIND[l.status]}>{l.status}</Badge>
      </div>
      <div className="kv quick" style={{ marginTop: 10 }}>
        <span className="muted">Type</span><span>{l.leave_type}</span>
        <span className="muted">From</span><span>{l.from_date}</span>
        <span className="muted">To</span><span>{l.to_date}</span>
        <span className="muted">Days</span><span>{l.days}</span>
        {l.reviewer_name && <><span className="muted">Reviewer</span><span>{l.reviewer_name}</span></>}
      </div>
      {l.reason && (
        <div className="small muted" style={{ marginTop: 8, borderTop: "1px solid var(--border,#e5e7eb)", paddingTop: 8 }}>
          Reason: {l.reason}
        </div>
      )}
      {l.review_note && (
        <div className="small" style={{ marginTop: 6, color: l.status === "rejected" ? "var(--bad,#e11d48)" : "var(--good,#16a34a)" }}>
          Note: {l.review_note}
        </div>
      )}
      {l.status === "pending" && canManage && (
        <div className="row" style={{ marginTop: 10, gap: 8, justifyContent: "flex-end" }}>
          <button className="btn sm" style={{ background: "var(--good,#16a34a)", color: "#fff" }}
            onClick={onApprove}>
            <CheckCircle size={14} /> Approve
          </button>
          <button className="btn danger sm" onClick={onReject}>
            <XCircle size={14} /> Reject
          </button>
        </div>
      )}
      {l.status === "pending" && !canManage && (
        <div className="row" style={{ marginTop: 8, justifyContent: "flex-end" }}>
          <button className="btn ghost sm danger" onClick={onCancel}>Cancel</button>
        </div>
      )}
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function Leaves() {
  const { session, can } = useAuth();
  const canManage = session?.role === "admin" || can("leaves.manage");
  const isStudent = session?.role === "student";
  const isStaff   = session?.role === "staff";
  // staff with a linked profile can apply; students can apply too
  const canApply  = isStudent || isStaff;

  // "pending" | "past" (approved+rejected) | "" (all — manager only)
  const [tab, setTab] = useState("pending");
  const [q, setQ] = useState("");
  const [dlg, setDlg] = useState(null);
  const [tick, setTick] = useState(0);

  // Determine the status filter to send
  const statusParam = tab === "past" ? "" : tab;   // past = no filter, then we filter client-side

  const state = useLoad(
    () => api(`/leaves${statusParam ? `?status=${statusParam}` : ""}`),
    [tick, tab]
  );
  const reload = () => setTick((t) => t + 1);

  const tabs = [
    { key: "pending",  label: "Pending" },
    { key: "past",     label: "Past" },
    ...(canManage ? [{ key: "", label: "All" }] : []),
  ];

  return (
    <>
      <PageHead
        title="Leaves"
        sub={canManage ? "Review and manage leave applications" : "Your leave applications"}
      >
        {canApply && (
          <button className="btn" onClick={() => setDlg({ type: "apply" })}>
            <Plus size={16} /> Apply for leave
          </button>
        )}
      </PageHead>

      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
        <div className="tabs" style={{ margin: 0 }}>
          {tabs.map((t) => (
            <button key={t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="search" style={{ margin: 0 }}>
          <Search size={16} />
          <input placeholder="Search by name, type, reason…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <Async state={state}>
        {(allLeaves) => {
          // For "past" tab: filter to approved+rejected client-side
          const base = tab === "past"
            ? allLeaves.filter((l) => l.status !== "pending")
            : allLeaves;

          const shown = q
            ? base.filter((l) =>
                (l.applicant_name || "").toLowerCase().includes(q.toLowerCase()) ||
                l.leave_type.toLowerCase().includes(q.toLowerCase()) ||
                (l.reason || "").toLowerCase().includes(q.toLowerCase()))
            : base;

          return (
            <>
              {base.length === 0 && (
                <div className="card">
                  <div className="muted" style={{ padding: "20px 0", textAlign: "center" }}>
                    <ClipboardList size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
                    <div>No {tab === "pending" ? "pending" : tab === "past" ? "past" : ""} leave applications found.</div>
                  </div>
                </div>
              )}
              {base.length > 0 && shown.length === 0 && (
                <div className="card">
                  <div className="muted" style={{ padding: "12px 0", textAlign: "center" }}>No results match "{q}".</div>
                </div>
              )}
              <div className="grid g2" style={{ alignItems: "start" }}>
                {shown.map((l) => (
                  <LeaveCard
                    key={l.id}
                    l={l}
                    canManage={canManage}
                    onApprove={() => setDlg({ type: "review", lid: l.id, action: "approved" })}
                    onReject={() => setDlg({ type: "review", lid: l.id, action: "rejected" })}
                    onCancel={async () => { await api(`/leaves/${l.id}`, { method: "DELETE" }); reload(); }}
                  />
                ))}
              </div>

              {dlg?.type === "apply" && (
                <ApplyLeaveModal isStudent={isStudent} onClose={() => setDlg(null)} onDone={reload} />
              )}
              {dlg?.type === "review" && (
                <ReviewModal lid={dlg.lid} action={dlg.action} onClose={() => setDlg(null)} onDone={reload} />
              )}
            </>
          );
        }}
      </Async>
    </>
  );
}
