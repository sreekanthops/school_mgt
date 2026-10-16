import { useState } from "react";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { Async, Badge, Confirm, Empty, FormModal, Meter, PageHead, useLoad } from "../components/ui.jsx";

const fields = [
  { key: "title", label: "Goal", required: true, full: true },
  { key: "target_year", label: "Target year", type: "number", min: 2000, max: 2100, required: true, default: new Date().getFullYear() + 1 },
  { key: "status", label: "Status", type: "select", options: ["Planned", "In Progress", "Completed"], default: "Planned" },
  { key: "progress", label: "Progress (%)", type: "number", min: 0, max: 100, required: true, default: 0 },
  { key: "description", label: "Description", type: "textarea", required: true, full: true },
];
const kind = { Completed: "good", "In Progress": "warn", Planned: "" };

export default function Goals() {
  const [tick, setTick] = useState(0);
  const [q, setQ] = useState("");
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api("/goals"), [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(d) => {
        const shown = q
          ? d.items.filter((g) =>
              g.title.toLowerCase().includes(q.toLowerCase()) ||
              g.description.toLowerCase().includes(q.toLowerCase()))
          : d.items;
        return (
        <>
          <PageHead title="Future Goals" sub="Where the school is headed">
            {d.can_manage && <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> Add goal</button>}
          </PageHead>
          <div className="search" style={{ marginBottom: 14 }}>
            <Search size={16} />
            <input placeholder="Search goals…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="grid g2">
            {shown.map((g) => (
              <div key={g.id} className="card">
                <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <b>{g.title}</b>
                    <div className="small muted">Target {g.target_year}</div>
                  </div>
                  <div className="row">
                    <Badge kind={kind[g.status]}>{g.status}</Badge>
                    {d.can_manage && (
                      <>
                        <button className="icon-btn" title="Edit" onClick={() => setDlg({ type: "edit", g })}><Pencil size={15} /></button>
                        <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", g })}><Trash2 size={15} /></button>
                      </>
                    )}
                  </div>
                </div>
                <p className="muted">{g.description}</p>
                <Meter pct={g.progress} kind={g.status === "Completed" ? "good" : undefined} />
                <div className="small muted" style={{ marginTop: 4 }}>{g.progress}% complete</div>
              </div>
            ))}
          </div>
          {d.items.length > 0 && shown.length === 0 && <div className="card"><Empty>No goals match "{q}".</Empty></div>}
          {d.items.length === 0 && <div className="card"><Empty>No goals added yet.</Empty></div>}
          {dlg?.type === "add" && (
            <FormModal title="Add goal" fields={fields} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api("/goals", { method: "POST", body: b }); reload(); }} />
          )}
          {dlg?.type === "edit" && (
            <FormModal title="Edit goal" fields={fields} initial={dlg.g} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api(`/goals/${dlg.g.id}`, { method: "PUT", body: b }); reload(); }} />
          )}
          {dlg?.type === "del" && (
            <Confirm title="Delete goal" message={`Delete "${dlg.g.title}"?`} onClose={() => setDlg(null)}
              onConfirm={async () => { await api(`/goals/${dlg.g.id}`, { method: "DELETE" }); reload(); }} />
          )}
        </>
        );
      }}
    </Async>
  );
}
