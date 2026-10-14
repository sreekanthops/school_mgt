import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, gradeLabel, inr } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Avatar, Badge, PageHead, tone, useLoad } from "../components/ui.jsx";

const GRADES = ["LKG", "UKG", ...Array.from({ length: 10 }, (_, i) => String(i + 1))];
const EMPTY = { admission_no: "", name: "", gender: "Male", dob: "", grade: "1", section: "A", guardian_name: "", phone: "", email: "", address: "", blood_group: "" };

export default function Students() {
  const nav = useNavigate();
  const { isAdmin } = useAuth();
  const [q, setQ] = useState("");
  const [grade, setGrade] = useState("");
  const [section, setSection] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [tick, setTick] = useState(0);
  const params = new URLSearchParams({ page, page_size: 12 });
  if (q) params.set("q", q);
  if (grade) params.set("grade", grade);
  if (section) params.set("section", section);
  const state = useLoad(() => api(`/students?${params}`), [q, grade, section, page, tick]);

  return (
    <>
      <PageHead title="Students" sub="Click a student for full details, marks and fees">
        {isAdmin && <button className="btn" onClick={() => setAdding((a) => !a)}>{adding ? "Close" : "+ Add student"}</button>}
      </PageHead>
      {adding && <AddStudent onDone={() => { setAdding(false); setTick((t) => t + 1); }} />}
      <div className="toolbar">
        <input placeholder="Search name or admission no." value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} style={{ minWidth: 240 }} />
        <select value={grade} onChange={(e) => { setGrade(e.target.value); setPage(1); }}>
          <option value="">All classes</option>
          {GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
        </select>
        <select value={section} onChange={(e) => { setSection(e.target.value); setPage(1); }}>
          <option value="">All sections</option>
          {["A", "B", "C"].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <Async state={state}>
        {(d) => (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table>
              <thead><tr><th>Student</th><th>Class</th><th>Guardian</th><th>Overall</th><th>Fee pending</th></tr></thead>
              <tbody>
                {d.items.map((s) => (
                  <tr key={s.id} className="click" onClick={() => nav(`/students/${s.id}`)}>
                    <td><div className="row"><Avatar name={s.name} /><div><b>{s.name}</b><div className="small muted">{s.admission_no}</div></div></div></td>
                    <td>{gradeLabel(s.grade)}-{s.section}</td>
                    <td>{s.guardian_name}<div className="small muted">{s.phone}</div></td>
                    <td>{s.overall_pct == null ? <span className="muted">–</span> : <Badge kind={tone(s.overall_pct)}>{s.overall_pct}% · {s.letter}</Badge>}</td>
                    <td>{s.fee_pending > 0 ? <Badge kind="warn">{inr(s.fee_pending)}</Badge> : <Badge kind="good">Clear</Badge>}</td>
                  </tr>
                ))}
                {d.items.length === 0 && <tr><td colSpan={5} className="empty">No students found.</td></tr>}
              </tbody>
            </table>
            <div className="pager" style={{ padding: 12 }}>
              <span className="muted small">{d.total} students · page {d.page} of {Math.max(1, Math.ceil(d.total / d.page_size))}</span>
              <button className="btn ghost sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
              <button className="btn ghost sm" disabled={page * d.page_size >= d.total} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </div>
        )}
      </Async>
    </>
  );
}

function AddStudent({ onDone }) {
  const [f, setF] = useState(EMPTY);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    const body = { ...f };
    ["email", "address", "blood_group"].forEach((k) => { if (!body[k]) body[k] = null; });
    try {
      await api("/students", { method: "POST", body });
      onDone();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="card" style={{ marginBottom: 16 }} onSubmit={submit}>
      <h2>New student</h2>
      {err && <div className="error">{err}</div>}
      <div className="form-grid">
        <Field label="Admission no." value={f.admission_no} onChange={set("admission_no")} required />
        <Field label="Full name" value={f.name} onChange={set("name")} required />
        <Sel label="Gender" value={f.gender} onChange={set("gender")} options={["Male", "Female", "Other"]} />
        <Field label="Date of birth" type="date" value={f.dob} onChange={set("dob")} required />
        <Sel label="Class" value={f.grade} onChange={set("grade")} options={GRADES} />
        <Sel label="Section" value={f.section} onChange={set("section")} options={["A", "B", "C"]} />
        <Field label="Guardian name" value={f.guardian_name} onChange={set("guardian_name")} required />
        <Field label="Phone" value={f.phone} onChange={set("phone")} required />
        <Field label="Email" type="email" value={f.email} onChange={set("email")} />
        <Sel label="Blood group" value={f.blood_group} onChange={set("blood_group")} options={["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]} />
        <Field label="Address" value={f.address} onChange={set("address")} />
      </div>
      <div style={{ marginTop: 14 }}><button className="btn" disabled={busy}>{busy ? "Saving…" : "Save student"}</button></div>
    </form>
  );
}

const Field = ({ label, ...p }) => <div className="field"><label>{label}</label><input {...p} /></div>;
const Sel = ({ label, options, ...p }) => (
  <div className="field"><label>{label}</label>
    <select {...p}>{options.map((o) => <option key={o} value={o}>{o || "—"}</option>)}</select></div>
);
