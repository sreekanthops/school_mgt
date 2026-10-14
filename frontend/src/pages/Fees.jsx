import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { api, GRADES, gradeLabel, inr } from "../api.js";
import { Async, Badge, Meter, PageHead, Stat, useLoad } from "../components/ui.jsx";

const KIND = { Paid: "good", Partial: "warn", Unpaid: "bad", "No fee set": "gray" };

export default function Fees() {
  const nav = useNavigate();
  const [grade, setGrade] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const params = new URLSearchParams();
  if (grade) params.set("grade", grade);
  if (status) params.set("status", status);
  if (q) params.set("q", q);
  const state = useLoad(() => api(`/fees?${params}`), [grade, status, q]);
  return (
    <>
      <PageHead title="Fee register" sub="Total, paid and pending for every student · click a row to record payments" />
      <div className="toolbar">
        <div className="search"><Search size={16} /><input placeholder="Search student" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">All classes</option>{GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>{["Paid", "Partial", "Unpaid", "No fee set"].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <Async state={state}>
        {(d) => (
          <>
            <div className="grid g4" style={{ marginBottom: 16 }}>
              <Stat label="Total fees" value={inr(d.summary.total)} tint="indigo" />
              <Stat label="Collected" value={inr(d.summary.paid)} sub={`${d.summary.collection_pct}%`} tint="green" />
              <Stat label="Pending" value={inr(d.summary.pending)} tint="rose" />
            </div>
            <div className="card flush" style={{ overflowX: "auto" }}>
              <table>
                <thead><tr><th>Student</th><th>Class</th><th>Total</th><th>Paid</th><th>Pending</th><th style={{ width: 140 }}>Progress</th><th>Status</th></tr></thead>
                <tbody>
                  {d.items.map((r) => (
                    <tr key={r.id} className="click" onClick={() => nav(`/students/${r.id}`)}>
                      <td><b>{r.name}</b><div className="small muted">{r.admission_no}</div></td>
                      <td>{gradeLabel(r.grade)}-{r.section}</td>
                      <td>{inr(r.total)}</td><td>{inr(r.paid)}</td><td>{inr(r.pending)}</td>
                      <td><Meter pct={r.total ? (r.paid * 100) / r.total : 0} kind={r.status === "Paid" ? "good" : r.status === "Partial" ? "warn" : "bad"} /></td>
                      <td><Badge kind={KIND[r.status]}>{r.status}</Badge></td>
                    </tr>
                  ))}
                  {d.items.length === 0 && <tr><td colSpan={7} className="empty">No records.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Async>
    </>
  );
}
