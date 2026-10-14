import { useState } from "react";
import { api } from "../api.js";
import { Async, Avatar, Badge, PageHead, useLoad } from "../components/ui.jsx";

export default function Staff() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);
  const state = useLoad(() => api(`/staff${q ? `?q=${encodeURIComponent(q)}` : ""}`), [q]);
  return (
    <>
      <PageHead title="Staff" sub="Faculty and administration" />
      <div className="toolbar"><input placeholder="Search by name or subject" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 260 }} /></div>
      <Async state={state}>
        {(rows) => (
          <div className="grid g3">
            {rows.map((s) => (
              <div key={s.id} className="card" onClick={() => setOpen(open === s.id ? null : s.id)} style={{ cursor: "pointer" }}>
                <div className="row">
                  <Avatar name={s.name} />
                  <div><b>{s.name}</b><div className="small muted">{s.designation} · {s.department}</div></div>
                </div>
                <div style={{ marginTop: 10 }} className="chip-list">
                  {s.class_teacher_of && <Badge kind="good">Class teacher {s.class_teacher_of}</Badge>}
                  {s.subjects && s.subjects.split(",").map((x) => <span key={x} className="chip">{x.trim()}</span>)}
                </div>
                {open === s.id && (
                  <dl className="kv" style={{ marginTop: 12 }}>
                    <dt>Employee ID</dt><dd>{s.employee_id}</dd>
                    <dt>Qualification</dt><dd>{s.qualification}</dd>
                    <dt>Experience</dt><dd>{s.experience_years} years</dd>
                    <dt>Joined</dt><dd>{s.joined_on}</dd>
                    <dt>Phone</dt><dd>{s.phone}</dd>
                    <dt>Email</dt><dd>{s.email}</dd>
                    <dt>About</dt><dd>{s.bio || "–"}</dd>
                  </dl>
                )}
              </div>
            ))}
            {rows.length === 0 && <div className="empty">No staff found.</div>}
          </div>
        )}
      </Async>
    </>
  );
}
