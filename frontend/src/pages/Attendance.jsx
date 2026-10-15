import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Check, CheckCheck, Save } from "lucide-react";
import { api, GRADES, gradeLabel } from "../api.js";
import { useAuth } from "../auth.jsx";
import { SECTIONS } from "../forms.js";
import { Async, Badge, DownloadButton, Meter, PageHead, Stat, tone, useLoad } from "../components/ui.jsx";

const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
const STATUS = [["P", "Present", "good"], ["L", "Late", "warn"], ["A", "Absent", "bad"]];

export default function Attendance() {
  const { can } = useAuth();
  const canMark = can("attendance.manage");
  const [tab, setTab] = useState(canMark ? "mark" : "report");
  const tabs = [...(canMark ? [["mark", "Mark attendance"]] : []), ["report", "Reports"], ["alerts", "Low attendance"]];
  return (
    <>
      <PageHead title="Attendance" sub="Daily attendance, reports and students who need attention" />
      <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "mark" && <Mark />}
      {tab === "report" && <Report />}
      {tab === "alerts" && <Alerts />}
    </>
  );
}

function Mark() {
  const [grade, setGrade] = useState("5");
  const [section, setSection] = useState("A");
  const [day, setDay] = useState(today());
  const [rows, setRows] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const state = useLoad(() => api(`/attendance/sheet?grade=${grade}&section=${section}&day=${day}`), [grade, section, day]);
  useEffect(() => {
    if (state.data) setRows(Object.fromEntries(state.data.students.map((s) => [s.id, s.status])));
    setMsg(null);
  }, [state.data]);
  const counts = useMemo(() => {
    const c = { P: 0, L: 0, A: 0, none: 0 };
    Object.values(rows).forEach((v) => { c[v ?? "none"] += 1; });
    return c;
  }, [rows]);
  const setAll = (st) => setRows(Object.fromEntries(Object.keys(rows).map((k) => [k, st])));
  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const entries = Object.entries(rows).filter(([, v]) => v).map(([id, status]) => ({ student_id: Number(id), status }));
      await api("/attendance/sheet", { method: "PUT", body: { grade, section, day, entries } });
      setMsg({ ok: true, text: `Saved for ${entries.length} students.` });
    } catch (x) {
      setMsg({ ok: false, text: x.message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="toolbar">
        <select value={grade} onChange={(e) => setGrade(e.target.value)} aria-label="Class">{GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}</select>
        <select value={section} onChange={(e) => setSection(e.target.value)} aria-label="Section">{SECTIONS.map((s) => <option key={s}>{s}</option>)}</select>
        <input type="date" value={day} max={today()} min={daysAgo(90)} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Date" style={{ width: "auto" }} />
        <button className="btn ghost sm" onClick={() => setAll("P")}><CheckCheck size={14} /> All present</button>
      </div>
      <Async state={state}>
        {(d) => (
          <div className="card flush">
            <table>
              <thead><tr><th>Student</th><th style={{ width: 280 }}>Status</th></tr></thead>
              <tbody>
                {d.students.map((s) => (
                  <tr key={s.id}>
                    <td><b>{s.name}</b><div className="small muted">{s.admission_no}</div></td>
                    <td>
                      <div className="seg" role="group" aria-label={`Attendance for ${s.name}`}>
                        {STATUS.map(([k, label, kind]) => (
                          <button key={k} type="button" className={`${rows[s.id] === k ? `on ${kind}` : ""} keep-seg`} aria-pressed={rows[s.id] === k}
                            onClick={() => setRows({ ...rows, [s.id]: k })}>{label}</button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
                {d.students.length === 0 && <tr><td colSpan={2} className="empty">No students in {gradeLabel(grade)}-{section}.</td></tr>}
              </tbody>
            </table>
            {d.students.length > 0 && (
              <div className="pager" style={{ gap: 12 }}>
                <span className="small muted">
                  {counts.P} present · {counts.L} late · {counts.A} absent{counts.none ? ` · ${counts.none} not marked` : ""}
                  {d.marked ? " · already saved for this day" : ""}
                </span>
                {msg && <span className="small" style={{ color: msg.ok ? "var(--good)" : "var(--bad)" }}>{msg.ok && <Check size={13} />} {msg.text}</span>}
                <button className="btn" onClick={save} disabled={busy || counts.none === d.students.length}><Save size={15} /> {busy ? "Saving…" : "Save attendance"}</button>
              </div>
            )}
          </div>
        )}
      </Async>
    </>
  );
}

function Report() {
  const [grade, setGrade] = useState("");
  const [section, setSection] = useState("");
  const [from, setFrom] = useState(daysAgo(29));
  const [to, setTo] = useState(today());
  const q = new URLSearchParams({ from, to });
  if (grade) q.set("grade", grade);
  if (section) q.set("section", section);
  const state = useLoad(() => api(`/attendance/report?${q}`), [grade, section, from, to]);
  return (
    <>
      <div className="toolbar">
        <select value={grade} onChange={(e) => setGrade(e.target.value)} aria-label="Class"><option value="">All classes</option>{GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}</select>
        <select value={section} onChange={(e) => setSection(e.target.value)} aria-label="Section"><option value="">All sections</option>{SECTIONS.map((s) => <option key={s}>{s}</option>)}</select>
        <label className="small muted">From <input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} style={{ width: "auto" }} /></label>
        <label className="small muted">To <input type="date" value={to} min={from} max={today()} onChange={(e) => e.target.value && setTo(e.target.value)} style={{ width: "auto" }} /></label>
        <DownloadButton path={`/export/attendance?${q}`} label="Download CSV" />
      </div>
      <Async state={state}>
        {(d) => (
          <>
            <div className="grid g3" style={{ marginBottom: 16 }}>
              <Stat label="Attendance" value={d.overall.pct == null ? "–" : `${d.overall.pct}%`} sub={`${d.overall.days} student-days recorded`} tint="green" />
              <Stat label="Absences" value={d.overall.absent} sub={`${d.overall.late} late arrivals`} tint="rose" />
              <Stat label={`Below ${d.threshold}%`} value={d.items.filter((i) => i.low).length} sub="students flagged" tint="amber" />
            </div>
            {d.trend.length > 1 && (
              <div className="card" style={{ marginBottom: 16 }}>
                <h2>Daily attendance %</h2>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={d.trend}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="day" fontSize={11} tickFormatter={(v) => v.slice(5)} /><YAxis domain={[0, 100]} fontSize={11} />
                    <Tooltip formatter={(v) => `${v}%`} /><Area dataKey="pct" name="Attendance" stroke="#16a34a" fill="#bbf7d0" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="card flush" style={{ overflowX: "auto" }}>
              <table>
                <thead><tr><th>Student</th><th>Class</th><th>Present</th><th>Late</th><th>Absent</th><th style={{ width: 150 }}>Attendance</th></tr></thead>
                <tbody>
                  {d.items.map((i) => (
                    <tr key={i.id}>
                      <td><Link to={`/students/${i.id}?tab=attendance`}><b>{i.name}</b></Link><div className="small muted">{i.admission_no}</div></td>
                      <td>{gradeLabel(i.grade)}-{i.section}</td><td>{i.present}</td><td>{i.late}</td><td>{i.absent}</td>
                      <td>{i.pct == null ? <span className="muted">no data</span> : <><Badge kind={i.low ? "bad" : tone(i.pct)}>{i.pct}%</Badge><Meter pct={i.pct} kind={i.low ? "bad" : undefined} /></>}</td>
                    </tr>
                  ))}
                  {d.items.length === 0 && <tr><td colSpan={6} className="empty">No students.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Async>
    </>
  );
}

function Alerts() {
  const state = useLoad(() => api("/attendance/alerts"));
  return (
    <Async state={state}>
      {(d) => (
        <div className="card">
          <h2><AlertTriangle size={18} style={{ verticalAlign: -3 }} /> Needs attention</h2>
          <p className="muted">Under {d.threshold}% over the last {d.window_days} days, or absent three school days in a row.</p>
          {d.items.length === 0 && <div className="empty">No student is flagged right now.</div>}
          {d.items.map((s) => (
            <div key={s.id} className="row" style={{ justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
              <Link to={`/students/${s.id}?tab=attendance`}><b>{s.name}</b><div className="small muted">{gradeLabel(s.grade)}-{s.section} · {s.admission_no}</div></Link>
              <div className="row" style={{ gap: 8 }}>
                {s.streak >= 3 && <Badge kind="warn">{s.streak} days absent in a row</Badge>}
                <Badge kind="bad">{s.pct}% · {s.absent} absent of {s.days}</Badge>
              </div>
            </div>
          ))}
        </div>
      )}
    </Async>
  );
}
