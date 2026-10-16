import { useState } from "react";
import { ImageIcon, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { Async, Confirm, Empty, FormModal, PageHead, Photo, PhotoUpload, useLoad } from "../components/ui.jsx";

const CATS = ["Sports", "Cultural", "Academic", "Celebration", "Campus", "Excursion", "Other"];
const fields = [
  { key: "title", label: "Title", required: true, full: true },
  { key: "category", label: "Category", type: "select", options: CATS, default: "Campus" },
  { key: "taken_on", label: "Date", type: "date", required: true },
  { key: "caption", label: "Caption", full: true },
];

function Pic({ g }) {
  if (!g.has_image) {
    return <div className="pic" style={{ background: "linear-gradient(135deg, var(--primary), var(--info))" }}><ImageIcon size={26} /></div>;
  }
  return <Photo kind="gallery" id={g.id} path={`/gallery/${g.id}/image`} has v={g.image_v} name={g.title} size={150} square />;
}

export default function Gallery() {
  const [tick, setTick] = useState(0);
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api("/gallery"), [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(d) => {
        const cats = [...new Set(d.items.map((i) => i.category))];
        const byCat = cat ? d.items.filter((i) => i.category === cat) : d.items;
        const items = q
          ? byCat.filter((i) =>
              i.title.toLowerCase().includes(q.toLowerCase()) ||
              (i.caption || "").toLowerCase().includes(q.toLowerCase()))
          : byCat;
        return (
          <>
            <PageHead title="Gallery" sub="Moments from around the school">
              {d.can_manage && <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> Add item</button>}
            </PageHead>
            <div className="search" style={{ marginBottom: 10 }}>
              <Search size={16} />
              <input placeholder="Search gallery…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <div className="tabs">
              <button className={cat === "" ? "on" : ""} onClick={() => setCat("")}>All</button>
              {cats.map((c) => <button key={c} className={cat === c ? "on" : ""} onClick={() => setCat(c)}>{c}</button>)}
            </div>
            <div className="gallery">
              {items.map((g) => (
                <div key={g.id} className="tile">
                  <Pic g={g} />
                  <div className="meta">
                    <b>{g.title}</b>
                    <div className="small muted">{g.category} · {g.taken_on}</div>
                    {g.caption && <div className="small">{g.caption}</div>}
                    {d.can_manage && (
                      <div className="row" style={{ marginTop: 8, flexWrap: "wrap" }}>
                        <PhotoUpload path={`/gallery/${g.id}/image`} label={g.has_image ? "Replace" : "Upload"} onDone={reload} />
                        <button className="icon-btn" title="Edit" onClick={() => setDlg({ type: "edit", g })}><Pencil size={15} /></button>
                        <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", g })}><Trash2 size={15} /></button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {d.items.length > 0 && items.length === 0 && <div className="card"><Empty>No items match your search.</Empty></div>}
            {d.items.length === 0 && <div className="card"><Empty>No gallery items yet.</Empty></div>}
            {dlg?.type === "add" && (
              <FormModal title="Add gallery item" fields={fields} onClose={() => setDlg(null)}
                onSubmit={async (b) => { await api("/gallery", { method: "POST", body: b }); reload(); }} />
            )}
            {dlg?.type === "edit" && (
              <FormModal title="Edit gallery item" fields={fields} initial={dlg.g} onClose={() => setDlg(null)}
                onSubmit={async (b) => { await api(`/gallery/${dlg.g.id}`, { method: "PUT", body: b }); reload(); }} />
            )}
            {dlg?.type === "del" && (
              <Confirm title="Delete gallery item" message={`Delete "${dlg.g.title}"?`} onClose={() => setDlg(null)}
                onConfirm={async () => { await api(`/gallery/${dlg.g.id}`, { method: "DELETE" }); reload(); }} />
            )}
          </>
        );
      }}
    </Async>
  );
}
