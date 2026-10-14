import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar,
  RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, gradeLabel, inr } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Avatar, Badge, Bar as Meter, PageHead, Stat, tone, useLoad } from "../components/ui.jsx";

const EXAMS = ["UT1", "Midterm", "UT2", "Final"];
const EXAM_COLORS = { UT1: "#93c5fd", Midterm: "#6366f1", UT2: "#a78bfa", Final: "#16a34a" };

export default function StudentDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [year, setYear] = useState(null); // null => current year
  const [view, setView] = useState("overview");
  const [tick, setTick] = useState(0);
  const state = useLoad(() => api(`/students/${id}${year ? `?year=${year}` : ""}`), [id, year, tick]);

  return (
    <Async state={state}>
      {(d) => {
        const s = d.student;
        const p = d.performance;
        return (
          <>
            <PageHead title={s.name} sub={<Link to="/students">← All students</Link>}>
              <div className="row">
                <span className="muted">Academic year</span>
                <select value={d.selected_year} onChange={(e) => { setYear(e.target.value); }}>
                  {d.years.map((y) => <option key={y} value={y}>{y}{y === d.years[0] ? " (current)" : ""}</option>)}
                </select>
              </div>
            </PageHead>

            <div className="card row" style={{ marginBottom: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
              <Avatar name={s.name} lg />
              <div style={{ flex: 1, minWidth: 260 }}>
                <h2 style={{ marginBottom: 4 }}>{s.name} <Badge>{gradeLabel(s.grade)}-{s.section}</Badge></h2>
                <dl className="kv">
                  <dt>Admission no.</dt><dd>{s.admission_no}</dd>
                  <dt>Gender / DOB</dt><dd>{s.gender} · {s.dob}</dd>
                  <dt>Guardian</dt><dd>{s.guardian_name} · {s.phone}</dd>
                  <dt>Email</dt><dd>{s.email || "–"}</dd>
                  <dt>Address</dt><dd>{s.address || "–"}</dd>
                  <dt>Blood group</dt><dd>{s.blood_group || "–"}</dd>
                </dl>
              </div>
              <div className="grid g3" style={{ flex: 1, minWidth: 300 }}>
                <Stat label="Overall" value={p.has_data ? `${p.overall_pct}%` : "–"} sub={p.has_data ? `Grade ${p.letter}` : "No marks"} />
                <Stat label="Section rank" value={d.rank ? `#${d.rank.rank}` : "–"} sub={d.rank ? `of ${d.rank.out_of}` : ""} />
                <Stat label="Fee pending" value={inr(d.fees.pending)} sub={d.fees.status} />
              </div>
            </div>

            <div className="tabs">
              {[["overview", "Overview"], ["marks", "All marks"], ["fees", "Fees"]].map(([k, l]) => (
                <button key={k} className={view === k ? "on" : ""} onClick={() => setView(k)}>{l}</button>
              ))}
            </div>

            {view === "overview" && <Overview d={d} />}
            {view === "marks" && <Marks p={p} />}
            {view === "fees" && <Fees d={d} sid={s.id} onChange={() => setTick((t) => t + 1)} />}
          </>
        );
      }}
    </Async>
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
            <Tooltip formatter={(v) => `${v}%`} /><Line type="monotone" dataKey="avg" name="Average %" stroke="#4f46e5" strokeWidth={3} dot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h2>Strength map</h2>
        <ResponsiveContainer width="100%" height={240}>
          <RadarChart data={subjData}>
            <PolarGrid /><PolarAngleAxis dataKey="subject" fontSize={10} /><PolarRadiusAxis domain={[0, 100]} fontSize={10} />
            <Radar dataKey="avg" name="Avg %" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.35} /><Tooltip />
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
                {s.trend !== 0 && <span className={`small ${s.trend > 0 ? "" : "muted"}`} style={{ marginLeft: 8, color: s.trend > 0 ? "var(--good)" : "var(--bad)" }}>{s.trend > 0 ? "▲" : "▼"} {Math.abs(s.trend)}</span>}</span>
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
              <Tooltip formatter={(v) => `${v}%`} /><Bar dataKey="overall_pct" name="Overall %" fill="#4f46e5" radius={[6, 6, 0, 0]} />
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
    <div className="card" style={{ padding: 0, overflowX: "auto" }}>
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

function Fees({ d, sid, onChange }) {
  const { isAdmin } = useAuth();
  const f = d.fees;
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState("UPI");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
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
      <div className="card">
        <h2>Fee summary · {f.year}</h2>
        <div className="grid g3" style={{ marginBottom: 14 }}>
          <Stat label="Total" value={inr(f.total)} /><Stat label="Paid" value={inr(f.paid)} /><Stat label="Pending" value={inr(f.pending)} />
        </div>
        <Meter pct={pct} kind={pct >= 100 ? "good" : pct >= 50 ? "warn" : "bad"} />
        <div className="small muted" style={{ marginTop: 6 }}>{pct}% paid · <Badge kind={f.status === "Paid" ? "good" : f.status === "Partial" ? "warn" : "bad"}>{f.status}</Badge></div>
        {isAdmin && f.pending > 0 && (
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
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <h2 style={{ padding: "18px 18px 0" }}>Payment history</h2>
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
