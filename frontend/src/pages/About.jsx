import { useState } from "react";
import { Calendar, MapPin, Pencil, Phone } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, FormModal, PageHead, useLoad } from "../components/ui.jsx";

const fields = [
  { key: "name", label: "School name", required: true, full: true },
  { key: "founded", label: "Founded (year)" },
  { key: "contact", label: "Contact" },
  { key: "address", label: "Address", full: true },
  { key: "about", label: "About", type: "textarea", full: true },
  { key: "mission", label: "Mission", type: "textarea", full: true },
  { key: "vision", label: "Vision", type: "textarea", full: true },
];

export default function About() {
  const { can, refresh } = useAuth();
  const [tick, setTick] = useState(0);
  const [editing, setEditing] = useState(false);
  const state = useLoad(() => api("/school"), [tick]);

  return (
    <Async state={state}>
      {(s) => (
        <>
          <PageHead title={s.name} sub="About our school">
            {can("school.manage") && <button className="btn" onClick={() => setEditing(true)}><Pencil size={15} /> Edit details</button>}
          </PageHead>
          <div className="grid g3" style={{ marginBottom: 16 }}>
            <div className="card row"><span className="stat-icon sky"><Calendar size={20} /></span><div><div className="small muted">Founded</div><b>{s.founded || "–"}</b></div></div>
            <div className="card row"><span className="stat-icon green"><Phone size={20} /></span><div><div className="small muted">Contact</div><b>{s.contact || "–"}</b></div></div>
            <div className="card row"><span className="stat-icon amber"><MapPin size={20} /></span><div><div className="small muted">Address</div><b>{s.address || "–"}</b></div></div>
          </div>
          <div className="grid g2">
            <div className="card" style={{ gridColumn: "1 / -1" }}><h3 style={{ marginTop: 0 }}>About</h3><p className="muted">{s.about || "Not added yet."}</p></div>
            <div className="card"><h3 style={{ marginTop: 0 }}>Mission</h3><p className="muted">{s.mission || "Not added yet."}</p></div>
            <div className="card"><h3 style={{ marginTop: 0 }}>Vision</h3><p className="muted">{s.vision || "Not added yet."}</p></div>
          </div>
          {editing && (
            <FormModal title="Edit school details" fields={fields} initial={s} onClose={() => setEditing(false)}
              onSubmit={async (b) => { await api("/school", { method: "PUT", body: b }); await refresh?.(); setTick((t) => t + 1); }} />
          )}
        </>
      )}
    </Async>
  );
}
