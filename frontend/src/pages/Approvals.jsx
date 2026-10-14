import { useState } from "react";
import { Check, X } from "lucide-react";
import { api, gradeLabel } from "../api.js";
import { Async, Empty, PageHead, Photo, useLoad } from "../components/ui.jsx";

export default function Approvals() {
  const [tick, setTick] = useState(0);
  const [err, setErr] = useState("");
  const state = useLoad(() => api("/photo-requests"), [tick]);

  async function act(id, verb) {
    setErr("");
    try {
      await api(`/students/${id}/photo-request/${verb}`, { method: "POST" });
      setTick((t) => t + 1);
    } catch (x) {
      setErr(x.message);
    }
  }

  return (
    <>
      <PageHead title="Photo Approvals" sub="Students' new profile photos wait here until approved" />
      {err && <div className="error">{err}</div>}
      <Async state={state}>
        {(rows) => (
          <div className="grid g3">
            {rows.map((r) => (
              <div key={r.student_id} className="card">
                <b>{r.name}</b>
                <div className="small muted" style={{ marginBottom: 12 }}>{gradeLabel(r.grade)}-{r.section}</div>
                <div className="row" style={{ justifyContent: "space-around", marginBottom: 14 }}>
                  <div style={{ textAlign: "center" }}>
                    <Photo kind="students" id={r.student_id} name={r.name} has={r.has_current} v={r.photo_v} size={84} />
                    <div className="small muted">Current</div>
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <Photo path={`/students/${r.student_id}/pending-photo`} id={r.student_id} name={r.name} has size={84} />
                    <div className="small muted">Requested</div>
                  </div>
                </div>
                <div className="row" style={{ justifyContent: "center" }}>
                  <button className="btn sm" onClick={() => act(r.student_id, "approve")}><Check size={14} /> Approve</button>
                  <button className="btn danger sm" onClick={() => act(r.student_id, "reject")}><X size={14} /> Reject</button>
                </div>
              </div>
            ))}
            {rows.length === 0 && <div className="card" style={{ gridColumn: "1 / -1" }}><Empty>No photos waiting for approval.</Empty></div>}
          </div>
        )}
      </Async>
    </>
  );
}
