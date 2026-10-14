import { useState } from "react";
import { MapPin, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { Async, Badge, Confirm, Empty, FormModal, PageHead, useLoad } from "../components/ui.jsx";

const CATS = ["Academic", "Sports", "Cultural", "Celebration", "Excursion", "Meeting", "Other"];
const fields = [
  { key: "title", label: "Title", required: true, full: true },
  { key: "date", label: "Date", type: "date", required: true },
  { key: "category", label: "Category", type: "select", options: CATS, default: "Academic" },
  { key: "location", label: "Location", required: true, full: true },
  { key: "description", label: "Description", type: "textarea", required: true, full: true },
];

export default function Events() {
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api("/events"), [tick]);
  const reload = () => setTick((t) => t + 1);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <Async state={state}>
      {(d) => (
        <>
          <PageHead title="Events" sub="Upcoming and past school events">
            {d.can_manage && <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> Add event</button>}
          </PageHead>
          <div className="grid">
            {d.items.map((e) => {
              const dt = new Date(e.date + "T00:00:00");
              return (
                <div key={e.id} className="card row" style={{ alignItems: "flex-start" }}>
                  <div className="timeline-date">
                    <div className="small">{dt.toLocaleString("en", { month: "short" })}</div>
                    <div style={{ fontSize: 20 }}>{dt.getDate()}</div>
                    <div className="small">{dt.getFullYear()}</div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div className="row" style={{ flexWrap: "wrap" }}>
                      <b>{e.title}</b>
                      <Badge>{e.category}</Badge>
                      {e.date >= today && <Badge kind="good">Upcoming</Badge>}
                    </div>
                    <div className="small muted"><MapPin size={12} /> {e.location}</div>
                    <p style={{ marginBottom: 0 }}>{e.description}</p>
                  </div>
                  {d.can_manage && (
                    <span>
                      <button className="icon-btn" title="Edit" onClick={() => setDlg({ type: "edit", e })}><Pencil size={15} /></button>
                      <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", e })}><Trash2 size={15} /></button>
                    </span>
                  )}
                </div>
              );
            })}
            {d.items.length === 0 && <div className="card"><Empty>No events yet.</Empty></div>}
          </div>
          {dlg?.type === "add" && (
            <FormModal title="Add event" fields={fields} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api("/events", { method: "POST", body: b }); reload(); }} />
          )}
          {dlg?.type === "edit" && (
            <FormModal title="Edit event" fields={fields} initial={dlg.e} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api(`/events/${dlg.e.id}`, { method: "PUT", body: b }); reload(); }} />
          )}
          {dlg?.type === "del" && (
            <Confirm title="Delete event" message={`Delete "${dlg.e.title}"?`} onClose={() => setDlg(null)}
              onConfirm={async () => { await api(`/events/${dlg.e.id}`, { method: "DELETE" }); reload(); }} />
          )}
        </>
      )}
    </Async>
  );
}
