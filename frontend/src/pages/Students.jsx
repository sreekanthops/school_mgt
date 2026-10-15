import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { GraduationCap, Plus, Search, Upload } from "lucide-react";
import { api, GRADES, gradeLabel, inr } from "../api.js";
import { useAuth } from "../auth.jsx";
import { SECTIONS, studentFields } from "../forms.js";
import ImportStudents from "../components/ImportStudents.jsx";
import { Async, Badge, DownloadButton, FormModal, PageHead, Photo, Secret, tone, useLoad } from "../components/ui.jsx";

export default function Students() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [search] = useSearchParams();
  const [grade, setGrade] = useState(GRADES.includes(search.get("grade")) ? search.get("grade") : "");
  const [section, setSection] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const [secret, setSecret] = useState(null);
  const [tick, setTick] = useState(0);
  const params = new URLSearchParams({ page, page_size: 12 });
  if (q) params.set("q", q);
  if (grade) params.set("grade", grade);
  if (section) params.set("section", section);
  const state = useLoad(() => api(`/students?${params}`), [q, grade, section, page, tick]);

  return (
    <>
      <PageHead title="Students" sub="Click a student to open their full profile">
        {can("students.view") && <DownloadButton path={`/export/students?format=csv${grade ? `&grade=${grade}` : ""}${section ? `&section=${section}` : ""}`} label="Export CSV" />}
        {can("students.view") && <DownloadButton path={`/export/students?format=pdf${grade ? `&grade=${grade}` : ""}${section ? `&section=${section}` : ""}`} label="PDF" />}
        {can("students.manage") && <button className="btn ghost" onClick={() => setImporting(true)}><Upload size={16} /> Import</button>}
        {can("students.manage") && can("school.manage") && <Link className="btn ghost" to="/new-year"><GraduationCap size={16} /> New year</Link>}
        {can("students.manage") && <button className="btn" onClick={() => setAdding(true)}><Plus size={16} /> Add student</button>}
      </PageHead>
      {importing && <ImportStudents onClose={() => setImporting(false)} onDone={() => setTick((t) => t + 1)} />}
      {adding && (
        <FormModal title="Add student" fields={studentFields} onClose={() => setAdding(false)}
          onSubmit={async (b) => {
            const r = await api("/students", { method: "POST", body: b });
            setSecret({ title: `${r.name} added`, username: r.login.username, password: r.login.temp_password, idLabel: "Student ID (login)" });
            setTick((t) => t + 1);
          }} />
      )}
      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
      <div className="toolbar">
        <div className="search"><Search size={16} /><input placeholder="Search name or student ID" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
        <select value={grade} onChange={(e) => { setGrade(e.target.value); setPage(1); }}>
          <option value="">All classes</option>
          {GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
        </select>
        <select value={section} onChange={(e) => { setSection(e.target.value); setPage(1); }}>
          <option value="">All sections</option>
          {SECTIONS.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <Async state={state}>
        {(d) => (
          <div className="card flush" style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Student</th><th>Class</th>
                  {d.detailed && <><th>Guardian</th><th>Overall</th></>}
                  {d.items[0]?.fee_pending !== undefined && <th>Fee pending</th>}
                </tr>
              </thead>
              <tbody>
                {d.items.map((s) => (
                  <tr key={s.id} className="click" onClick={() => nav(`/students/${s.id}`)}>
                    <td><div className="row"><Photo kind="students" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} />
                      <div><b>{s.name}</b>{d.detailed && <div className="small muted">{s.admission_no}</div>}</div></div></td>
                    <td>{gradeLabel(s.grade)}-{s.section}</td>
                    {d.detailed && (
                      <>
                        <td>{s.guardian_name}<div className="small muted">{s.phone}</div></td>
                        <td>{s.overall_pct == null ? <span className="muted">–</span> : <Badge kind={tone(s.overall_pct)}>{s.overall_pct}% · {s.letter}</Badge>}</td>
                      </>
                    )}
                    {s.fee_pending !== undefined && <td>{s.fee_pending > 0 ? <Badge kind="warn">{inr(s.fee_pending)}</Badge> : <Badge kind="good">Clear</Badge>}</td>}
                  </tr>
                ))}
                {d.items.length === 0 && <tr><td colSpan={5} className="empty">No students found.</td></tr>}
              </tbody>
            </table>
            <div className="pager">
              <span className="muted small">{d.total} students · page {d.page} of {Math.max(1, Math.ceil(d.total / d.page_size))}</span>
              <button className="btn ghost sm keep" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
              <button className="btn ghost sm keep" disabled={page * d.page_size >= d.total} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </div>
        )}
      </Async>
    </>
  );
}
