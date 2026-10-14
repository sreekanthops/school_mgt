import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, Plus, Trash2 } from "lucide-react";
import { api, gradeLabel } from "../api.js";
import { Async, Badge, Confirm, Empty, FormModal, PageHead, useLoad } from "../components/ui.jsx";

const chapterFields = [
  { key: "number", label: "Chapter no.", type: "number", min: 1, max: 200, required: true },
  { key: "title", label: "Title", required: true },
  { key: "description", label: "Description", type: "textarea", full: true },
];

export default function SubjectDetail() {
  const { id } = useParams();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api(`/subjects/${id}`), [id, tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(s) => (
        <>
          <Link to="/subjects" className="backlink"><ArrowLeft size={14} /> Subjects</Link>
          <PageHead title={s.name} sub={gradeLabel(s.grade)}>
            {s.can_manage && (
              <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> Add chapter</button>
            )}
          </PageHead>
          <div className="grid g2" style={{ gridTemplateColumns: "2fr 1fr" }}>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Chapters <Badge>{s.chapters.length}</Badge></h3>
              {s.chapters.map((c) => (
                <div key={c.id} className="chapter">
                  <span className="num">{c.number}</span>
                  <div style={{ flex: 1 }}>
                    <b>{c.title}</b>
                    {c.description && <div className="muted">{c.description}</div>}
                  </div>
                  {s.can_manage && (
                    <span>
                      <button className="icon-btn" title="Edit" onClick={() => setDlg({ type: "edit", c })}><Pencil size={15} /></button>
                      <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", c })}><Trash2 size={15} /></button>
                    </span>
                  )}
                </div>
              ))}
              {s.chapters.length === 0 && <Empty>No chapters added yet.</Empty>}
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Teachers</h3>
              {s.teachers.length === 0 && <div className="muted">No teacher assigned.</div>}
              {s.teachers.map((t) => (
                <div key={t.id} style={{ marginBottom: 8 }}>
                  <Link to={`/staff/${t.id}`}><b>{t.name}</b></Link>
                  <div className="small muted">{t.designation}</div>
                </div>
              ))}
            </div>
          </div>
          {dlg?.type === "add" && (
            <FormModal title="Add chapter" fields={chapterFields} initial={{ number: s.chapters.length + 1 }} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api(`/subjects/${id}/chapters`, { method: "POST", body: b }); reload(); }} />
          )}
          {dlg?.type === "edit" && (
            <FormModal title="Edit chapter" fields={chapterFields} initial={dlg.c} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api(`/chapters/${dlg.c.id}`, { method: "PUT", body: b }); reload(); }} />
          )}
          {dlg?.type === "del" && (
            <Confirm title="Delete chapter" message={`Delete chapter ${dlg.c.number}: ${dlg.c.title}?`} onClose={() => setDlg(null)}
              onConfirm={async () => { await api(`/chapters/${dlg.c.id}`, { method: "DELETE" }); reload(); }} />
          )}
        </>
      )}
    </Async>
  );
}
