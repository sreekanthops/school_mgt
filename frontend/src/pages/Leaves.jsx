import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle, ClipboardList, XCircle } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, Modal, PageHead, useLoad } from "../components/ui.jsx";

const STATUS_KIND = { pending: "warn", approved: "good", rejected: "bad" };
const LEAVE_TYPES = ["Casual", "Sick", "Earned", "Maternity", "Paternity", "Unpaid", "Other"];

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

export default function Leaves() {
  const { session, can } = useAuth();
  const canManage = session?.role === "admin" || can("leaves.manage");
  const [filter, setFilter] = useState("pending");
  const [dlg, setDlg] = useState(null);
  const [tick, setTick] = useState(0);
  const state = useLoad(
    () => api(`/leaves${filter ? `?status=${filter}` : ""}`),
    [tick, filter]
  );
  const reload = () => setTick((t) => t + 1);

  return (
    <>
      <PageHead
        title="Staff Leaves"
        sub={canManage ? "Review and manage staff leave applications" : "Your leave applications"}
      />

      <div className="tabs" style={{ marginBottom: 16 }}>
        {["pending", "approved", "rejected", ""].map((s) => (
          <button key={s || "all"} className={filter === s ? "on" : ""} onClick={() => setFilter(s)}>
            {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <Async state={state}>
        {(leaves) => (
          <>
            {leaves.length === 0 && (
              <div className="card">
                <div className="muted" style={{ padding: "20px 0", textAlign: "center" }}>
                  <ClipboardList size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
                  <div>No {filter || ""} leave applications found.</div>
                </div>
              </div>
            )}
            <div className="grid g2" style={{ alignItems: "start" }}>
              {leaves.map((l) => (
                <div key={l.id} className="card" style={{ padding: "14px 16px" }}>
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
                        onClick={() => setDlg({ lid: l.id, action: "approved" })}>
                        <CheckCircle size={14} /> Approve
                      </button>
                      <button className="btn danger sm"
                        onClick={() => setDlg({ lid: l.id, action: "rejected" })}>
                        <XCircle size={14} /> Reject
                      </button>
                    </div>
                  )}
                  {l.status === "pending" && !canManage && (
                    <div className="row" style={{ marginTop: 8, justifyContent: "flex-end" }}>
                      <button className="btn ghost sm danger"
                        onClick={async () => { await api(`/leaves/${l.id}`, { method: "DELETE" }); reload(); }}>
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            {dlg && (
              <ReviewModal lid={dlg.lid} action={dlg.action} onClose={() => setDlg(null)} onDone={reload} />
            )}
          </>
        )}
      </Async>
    </>
  );
}
