import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar,
  RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ArrowLeft, Check, Clock, Pencil, Plus, Trash2, X } from "lucide-react";
import { api, gradeLabel, inr } from "../api.js";
import { useAuth } from "../auth.jsx";
import { studentFields } from "../forms.js";
import { Async, Badge, Confirm, FormModal, Meter, PageHead, Photo, PhotoUpload, Stat, tone, useLoad } from "../components/ui.jsx";

const EXAMS = ["UT1", "Midterm", "UT2", "Final"];
const EXAM_COLORS = { UT1: "#93c5fd", Midterm: "#6366f1", UT2: "#a78bfa", Final: "#16a34a" };

export default function StudentDetail({ me = false }) {
  const params = useParams();
  const { session } = useAuth();
  const id = me ? session.student_id : params.id;
  const nav = useNavigate();
  const [year, setYear] = useState(null);
  const [search] = useSearchParams();
  const [view, setView] = useState(["overview", "marks", "fees"].includes(search.get("tab")) ? search.get("tab") : "overview");
  const [tick, setTick] = useState(0);
  const [modal, setModal] = useState(null);
  const refresh = () => setTick((t) => t + 1);
  const state = useLoad(() => api(`/students/${id}${year ? `?year=${year}` : ""}`), [id, year, tick]);

  return (
    <Async state={state}>
      {(d) => {
        const s = d.student;
        const p = d.performance;
        const can = d.can;
        const tabs = [["overview", "Overview"], ["marks", "All marks"], ...(d.fees ? [["fees", "Fees"]] : [])];
        return (
          <>
            {!me && <Link to="/students" className="backlink"><ArrowLeft size={14} /> All students</Link>}
            <PageHead title={me ? "My Profile" : s.name} sub={`${gradeLabel(s.grade)}-${s.section} · Student ID ${s.admission_no}`}>
              <span className="muted">Academic year</span>
              <select style={{ width: "auto" }} value={d.selected_year} onChange={(e) => setYear(e.target.value)}>
                {d.years.map((y) => <option key={y} value={y}>{y}{y === d.years[0] ? " (current)" : ""}</option>)}
              </select>
              {can.marks && <button className="btn" onClick={() => setModal("marks")}><Plus size={16} /> Enter marks</button>}
              {can.edit && <button className="btn ghost" onClick={() => setModal("edit")}><Pencil size={16} /> Edit</button>}
              {can.edit && <button className="btn danger" onClick={() => setModal("delete")}><Trash2 size={16} /> Delete</button>}
            </PageHead>

            {modal === "edit" && <FormModal title="Edit student" fields={studentFields} initial={s} onClose={() => setModal(null)}
              onSubmit={async (b) => { await api(`/students/${id}`, { method: "PUT", body: b }); refresh(); }} />}
            {modal === "delete" && <Confirm title="Delete student" message={`Delete ${s.name} and all of their marks and fee records? This cannot be undone.`}
              onClose={() => setModal(null)} onConfirm={async () => { await api(`/students/${id}`, { method: "DELETE" }); nav("/students"); }} />}
            {modal === "marks" && <MarksForm sid={id} year={d.selected_year} onClose={() => setModal(null)} onDone={refresh} />}

            <div className="card" style={{ marginBottom: 16 }}>
              <div className="hero-cover" />
              <div className="hero">
                <Photo kind="students" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} size={96} />
                <div style={{ flex: 1, minWidth: 260, paddingTop: 12 }}>
                  <h2 style={{ marginBottom: 6 }}>{s.name} <Badge>{gradeLabel(s.grade)}-{s.section}</Badge></h2>
                  <dl className="kv">
                    <dt>Gender / DOB</dt><dd>{s.gender} · {s.dob}</dd>
                    <dt>Guardian</dt><dd>{s.guardian_name} · {s.phone}</dd>
                    <dt>Email</dt><dd>{s.email || "–"}</dd>
                    <dt>Address</dt><dd>{s.address || "–"}</dd>
                    <dt>Blood group</dt><dd>{s.blood_group || "–"}</dd>
                  </dl>
                  <PhotoControls d={d} sid={s.id} onChange={refresh} />
                </div>
                <div className="grid g3" style={{ flex: 1, minWidth: 300 }}>
                  <Stat label="Overall" value={p.has_data ? `${p.overall_pct}%` : "–"} sub={p.has_data ? `Grade ${p.letter}` : "No marks"} />
                  <Stat label="Section rank" value={d.rank ? `#${d.rank.rank}` : "–"} sub={d.rank ? `of ${d.rank.out_of}` : ""} />
                  {d.fees && <Stat label="Fee pending" value={inr(d.fees.pending)} sub={d.fees.status} />}
                </div>
              </div>
            </div>

            <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)}>{l}</button>)}</div>
            {view === "overview" && <Overview d={d} />}
            {view === "marks" && <Marks p={p} />}
            {view === "fees" && d.fees && <Fees d={d} sid={s.id} canManage={can.fees} onChange={refresh} />}
          </>
        );
      }}
    </Async>
  );
}

/** Photo actions. Students only *request*; staff with permission set directly; approvers see pending requests. */
function PhotoControls({ d, sid, onChange }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const act = async (verb) => {
    setBusy(true);
    setErr("");
    try { await api(`/students/${sid}/photo-request/${verb}`, { method: "POST" }); onChange(); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <div style={{ marginTop: 12 }}>
      <div className="row" style={{ flexWrap: "wrap" }}>
        {d.can.edit && <PhotoUpload path={`/students/${sid}/photo`} onDone={onChange} />}
        {d.can.photo_request && <PhotoUpload path={`/students/${sid}/photo-request`} label="Request new photo" onDone={onChange} />}
      </div>
      {d.can.photo_request && d.photo_pending && <div className="notice" style={{ marginTop: 8 }}><Clock size={14} style={{ verticalAlign: -2 }} /> Your new photo is waiting for admin approval. Your current photo stays until then.</div>}
      {d.can.approve && d.photo_pending && (
        <div className="notice" style={{ marginTop: 8 }}>
          <b>Pending photo request</b>
          <div className="row" style={{ marginTop: 8 }}>
            <Photo kind="students" id={sid} name="Pending" has size={64} path={`/students/${sid}/pending-photo`} />
            <button className="btn sm" disabled={busy} onClick={() => act("approve")}><Check size={14} /> Approve</button>
            <button className="btn danger sm" disabled={busy} onClick={() => act("reject")}><X size={14} /> Reject</button>
          </div>
        </div>
      )}
      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
    </div>
  );
}

function MarksForm({ sid, year, onClose, onDone }) {
  const subs = useLoad(() => api(`/subjects-for-marks?sid=${sid}`), [sid]);
  if (subs.loading) return null;
  const options = (subs.data || []).map((x) => [String(x.id), x.name]);
  const fields = [
    { key: "subject_id", label: "Subject", type: "select", options: options.length ? options : [["", "No subjects for this class"]], required: true, default: options[0]?.[0] },
    { key: "exam", label: "Test", type: "select", options: [["UT1", "UT1 (out of 25)"], ["Midterm", "Midterm (out of 50)"], ["UT2", "UT2 (out of 25)"], ["Final", "Final (out of 100)"]], default: "UT1" },
    { key: "score", label: "Score", type: "number", required: true, min: 0 },
  ];
  return (
    <FormModal title={`Enter marks · ${year}`} fields={fields} onClose={onClose}
      onSubmit={async (b) => { await api(`/students/${sid}/marks`, { method: "POST", body: { ...b, subject_id: Number(b.subject_id), academic_year: year } }); onDone(); }} />
  );
}

function Overview({ d }) {
  const p = d.performance;
  if (!p.has_data) return <div className="card empty">No marks recorded for {d.selected_year}.</div>;
  const subjData = p.subjects.map((s) => ({ subject: s.subject, ...s.exams, avg: s.avg_pct }));
  const examData = p.exams.map((e) => ({ exam: e.exam, avg: e.avg_pct }));
  return (
    <div className="grid g2">
      <div className="card" style={{ gridColumn: "1 / -1" }}>
        <h2>Subject performance by test ({gradeLabel(p.grade)}, {p.year})</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={subjData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="subject" fontSize={11} interval={0} angle={-20} textAnchor="end" height={60} />
            <YAxis domain={[0, 100]} fontSize={12} /><Tooltip formatter={(v) => `${v}%`} /><Legend verticalAlign="top" />
            {EXAMS.map((e) => <Bar key={e} dataKey={e} fill={EXAM_COLORS[e]} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h2>Progress across tests</h2>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={examData}>
            <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="exam" fontSize={12} /><YAxis domain={[0, 100]} fontSize={12} />
            <Tooltip formatter={(v) => `${v}%`} /><Line type="monotone" dataKey="avg" name="Average %" stroke="#5b4bdb" strokeWidth={3} dot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h2>Strength map</h2>
        <ResponsiveContainer width="100%" height={240}>
          <RadarChart data={subjData}>
            <PolarGrid /><PolarAngleAxis dataKey="subject" fontSize={10} /><PolarRadiusAxis domain={[0, 100]} fontSize={10} />
            <Radar dataKey="avg" name="Avg %" stroke="#5b4bdb" fill="#5b4bdb" fillOpacity={0.35} /><Tooltip />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h2>Where the student is lacking</h2>
        {p.insights.map((t, i) => <div key={i} className={`insight ${p.weak_subjects.length ? "" : "ok"}`}>{t}</div>)}
        {p.strong_subjects.length > 0 && <div className="muted small">Strong in: {p.strong_subjects.join(", ")}</div>}
      </div>
      <div className="card">
        <h2>Subject averages</h2>
        {p.subjects.map((s) => (
          <div key={s.subject} style={{ marginBottom: 10 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span>{s.subject}</span>
              <span><Badge kind={tone(s.avg_pct)}>{s.avg_pct}%</Badge>
                {s.trend !== 0 && <span className="small" style={{ marginLeft: 8, color: s.trend > 0 ? "var(--good)" : "var(--bad)" }}>{s.trend > 0 ? "▲" : "▼"} {Math.abs(s.trend)}</span>}</span>
            </div>
            <Meter pct={s.avg_pct} />
          </div>
        ))}
      </div>
      {d.history.length > 1 && (
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <h2>Year-wise history</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={d.history.map((h) => ({ ...h, label: `${h.year} (${gradeLabel(h.grade)})` }))}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" fontSize={12} /><YAxis domain={[0, 100]} fontSize={12} />
              <Tooltip formatter={(v) => `${v}%`} /><Bar dataKey="overall_pct" name="Overall %" fill="#5b4bdb" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function Marks({ p }) {
  if (!p.has_data) return <div className="card empty">No marks recorded for this year.</div>;
  const bySubject = {};
  p.marks.forEach((m) => { (bySubject[m.subject] ||= {})[m.exam] = m; });
  return (
    <div className="card flush" style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th>Subject</th>{EXAMS.map((e) => <th key={e}>{e}</th>)}<th>Average</th></tr></thead>
        <tbody>
          {p.subjects.slice().sort((a, b) => a.subject.localeCompare(b.subject)).map((s) => (
            <tr key={s.subject}>
              <td><b>{s.subject}</b></td>
              {EXAMS.map((e) => {
                const m = bySubject[s.subject]?.[e];
                return <td key={e}>{m ? <><b>{m.score}</b><span className="muted"> / {m.max}</span> <Badge kind={tone(m.pct)}>{m.pct}%</Badge></> : "–"}</td>;
              })}
              <td><Badge kind={tone(s.avg_pct)}>{s.avg_pct}%</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Fees({ d, sid, canManage, onChange }) {
  const f = d.fees;
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState("UPI");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [setting, setSetting] = useState(false);
  const pct = f.total ? Math.round((f.paid * 100) / f.total) : 0;

  async function pay(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api(`/students/${sid}/payments`, { method: "POST", body: { academic_year: f.year, amount: Number(amount), mode } });
      setAmount("");
      onChange();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="grid g2">
      {setting && <FormModal title={`Set total fee · ${f.year}`} onClose={() => setSetting(false)} initial={{ total_amount: f.total }}
        fields={[{ key: "total_amount", label: "Total fee (₹)", type: "number", min: 0, required: true }]}
        onSubmit={async (b) => { await api(`/students/${sid}/fees`, { method: "PUT", body: { academic_year: f.year, total_amount: b.total_amount } }); onChange(); }} />}
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>Fee summary · {f.year}</h2>
          {canManage && <button className="btn ghost sm" onClick={() => setSetting(true)}><Pencil size={13} /> Set total</button>}
        </div>
        <div className="grid g3" style={{ marginBottom: 14 }}>
          <Stat label="Total" value={inr(f.total)} /><Stat label="Paid" value={inr(f.paid)} /><Stat label="Pending" value={inr(f.pending)} />
        </div>
        <Meter pct={pct} kind={pct >= 100 ? "good" : pct >= 50 ? "warn" : "bad"} />
        <div className="small muted" style={{ marginTop: 6 }}>{pct}% paid · <Badge kind={f.status === "Paid" ? "good" : f.status === "Partial" ? "warn" : "bad"}>{f.status}</Badge></div>
        {canManage && f.pending > 0 && (
          <form onSubmit={pay} style={{ marginTop: 16 }}>
            <h3>Record payment</h3>
            {err && <div className="error">{err}</div>}
            <div className="toolbar">
              <input type="number" min="1" max={f.pending} step="1" placeholder={`Up to ${f.pending}`} value={amount} onChange={(e) => setAmount(e.target.value)} required />
              <select value={mode} onChange={(e) => setMode(e.target.value)}>{["Cash", "UPI", "Card", "Cheque", "Bank Transfer"].map((m) => <option key={m}>{m}</option>)}</select>
              <button className="btn" disabled={busy}>Add payment</button>
            </div>
          </form>
        )}
      </div>
      <div className="card flush" style={{ overflowX: "auto" }}>
        <h2 style={{ padding: "20px 20px 0" }}>Payment history</h2>
        <table>
          <thead><tr><th>Date</th><th>Receipt</th><th>Mode</th><th>Amount</th></tr></thead>
          <tbody>
            {f.payments.map((x) => <tr key={x.id}><td>{x.paid_on}</td><td>{x.receipt_no}</td><td>{x.mode}</td><td>{inr(x.amount)}</td></tr>)}
            {f.payments.length === 0 && <tr><td colSpan={4} className="empty">No payments yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
