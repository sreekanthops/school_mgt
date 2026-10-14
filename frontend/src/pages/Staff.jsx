import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronUp, Plus, Search } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { staffFields } from "../forms.js";
import { Async, Badge, FormModal, PageHead, Photo, useLoad } from "../components/ui.jsx";

export default function Staff() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);
  const [adding, setAdding] = useState(false);
  const [tick, setTick] = useState(0);
  const state = useLoad(() => api(`/staff${q ? `?q=${encodeURIComponent(q)}` : ""}`), [q, tick]);

  return (
    <>
      <PageHead title="Staff" sub="Use Quick view for a summary, or open a member for the full profile">
        {can("staff.manage") && <button className="btn" onClick={() => setAdding(true)}><Plus size={16} /> Add staff</button>}
      </PageHead>
      {adding && (
        <FormModal title="Add staff member" fields={staffFields} onClose={() => setAdding(false)}
          onSubmit={async (b) => { await api("/staff", { method: "POST", body: b }); setTick((t) => t + 1); }} />
      )}
      <div className="toolbar">
        <div className="search"><Search size={16} /><input placeholder="Search name or subject" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      <Async state={state}>
        {(rows) => (
          <div className="grid g4">
            {rows.map((s) => (
              <div key={s.id} className="card person">
                <div className="go" onClick={() => nav(`/staff/${s.id}`)} role="link" tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && nav(`/staff/${s.id}`)}>
                  <Photo kind="staff" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} size={72} />
                  <b>{s.name}</b>
                  <div className="muted">{s.designation}</div>
                  <Badge>{s.department}</Badge>
                </div>
                <div className="person-actions">
                  <button className="btn ghost sm" onClick={() => setOpen(open === s.id ? null : s.id)}>
                    Quick view {open === s.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  <button className="btn sm" onClick={() => nav(`/staff/${s.id}`)}>Full profile</button>
                </div>
                {open === s.id && (
                  <dl className="kv quick">
                    <dt>Subjects</dt><dd>{s.subjects || "–"}</dd>
                    <dt>Class teacher</dt><dd>{s.class_teacher_of || "–"}</dd>
                  </dl>
                )}
              </div>
            ))}
            {rows.length === 0 && <div className="card empty" style={{ gridColumn: "1 / -1" }}>No staff found.</div>}
          </div>
        )}
      </Async>
    </>
  );
}
