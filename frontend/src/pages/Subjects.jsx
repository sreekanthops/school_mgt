import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BookOpen, Pencil, Plus, Trash2 } from "lucide-react";
import { api, gradeLabel } from "../api.js";
import { Async, Badge, Confirm, FormModal, PageHead, useLoad } from "../components/ui.jsx";

const nameField = [{ key: "name", label: "Subject name", required: true, full: true }];

export default function Subjects() {
  const [tick, setTick] = useState(0);
  const [search] = useSearchParams();
  const [grade, setGrade] = useState(search.get("grade") || "1");
  const [q, setQ] = useState("");
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api("/subjects"), [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(d) => {
        const cur = d.grades.find((g) => g.grade === grade) ?? d.grades[0];
        const shown = q
          ? cur.subjects.filter((s) => s.name.toLowerCase().includes(q.toLowerCase()))
          : cur.subjects;
        return (
          <>
            <PageHead title="Subjects" sub="Pick a class, then open a subject to see its chapters">
              {d.can_manage && <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> Add subject</button>}
            </PageHead>
            <div className="tabs">
              {d.grades.map((g) => (
                <button key={g.grade} className={g.grade === grade ? "on" : ""} onClick={() => setGrade(g.grade)}>
                  {gradeLabel(g.grade)} <span className="small">({g.subjects.length})</span>
                </button>
              ))}
            </div>
            <div className="search" style={{ marginBottom: 14 }}>
              <Search size={16} />
              <input placeholder="Search subjects…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <div className="grid g3">
              {shown.map((s) => (
                <div key={s.id} className="card subject-card">
                  <div className="top">
                    <Link to={`/subjects/${s.id}`} className="row" style={{ color: "inherit" }}>
                      <span className="stat-icon indigo"><BookOpen size={20} /></span>
                      <b>{s.name}</b>
                    </Link>
                    {d.can_manage && (
                      <span>
                        <button className="icon-btn" title="Rename" onClick={() => setDlg({ type: "edit", s })}><Pencil size={15} /></button>
                        <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", s })}><Trash2 size={15} /></button>
                      </span>
                    )}
                  </div>
                  <div className="row"><Badge>{s.chapters} chapters</Badge></div>
                  <div className="small muted">{s.teachers.length ? `Taught by ${s.teachers.join(", ")}` : "No teacher assigned"}</div>
                </div>
              ))}
              {cur.subjects.length > 0 && shown.length === 0 && <div className="card empty" style={{ gridColumn: "1 / -1" }}>No subjects match "{q}".</div>}
              {cur.subjects.length === 0 && <div className="card empty" style={{ gridColumn: "1 / -1" }}>No subjects for {gradeLabel(cur.grade)} yet.</div>}
            </div>
            {dlg?.type === "add" && (
              <FormModal title={`Add subject to ${gradeLabel(grade)}`} fields={nameField} onClose={() => setDlg(null)}
                onSubmit={async (b) => { await api("/subjects", { method: "POST", body: { ...b, grade } }); reload(); }} />
            )}
            {dlg?.type === "edit" && (
              <FormModal title="Rename subject" fields={nameField} initial={dlg.s} onClose={() => setDlg(null)}
                onSubmit={async (b) => { await api(`/subjects/${dlg.s.id}`, { method: "PUT", body: b }); reload(); }} />
            )}
            {dlg?.type === "del" && (
              <Confirm title="Delete subject" message={`Delete ${dlg.s.name} with its chapters and marks? This cannot be undone.`}
                onClose={() => setDlg(null)} onConfirm={async () => { await api(`/subjects/${dlg.s.id}`, { method: "DELETE" }); reload(); }} />
            )}
          </>
        );
      }}
    </Async>
  );
}
