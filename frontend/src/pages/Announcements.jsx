import { useState } from "react";
import { Megaphone, Pin, PinOff, Plus, Search, Trash2 } from "lucide-react";
import { api, GRADES, gradeLabel } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, Confirm, Modal, PageHead, useLoad } from "../components/ui.jsx";

const WHO = { all: "Everyone", staff: "Staff only", students: "Students only", class: "One class" };

function Composer({ onClose, onDone }) {
  const [f, setF] = useState({ title: "", body: "", audience: "all", grade: "5", pinned: false });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("/announcements", { method: "POST", body: { ...f, grade: f.audience === "class" ? f.grade : null } });
      onDone();
      onClose();
    } catch (x) {
      setErr(x.message);
      setBusy(false);
    }
  }
  return (
    <Modal title="New announcement" onClose={onClose} wide>
      <form onSubmit={submit}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label htmlFor="an-t">Title *</label>
            <input id="an-t" value={f.title} maxLength={150} required onChange={(e) => setF({ ...f, title: e.target.value })} />
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label htmlFor="an-b">Message *</label>
            <textarea id="an-b" rows={5} value={f.body} maxLength={2000} required onChange={(e) => setF({ ...f, body: e.target.value })} />
            <div className="small muted">{f.body.length} / 2000</div>
          </div>
          <div className="field">
            <label htmlFor="an-a">Send to</label>
            <select id="an-a" value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })}>
              {Object.entries(WHO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          {f.audience === "class" && (
            <div className="field">
              <label htmlFor="an-g">Class</label>
              <select id="an-g" value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })}>
                {GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
              </select>
            </div>
          )}
          <label className="check" style={{ gridColumn: "1 / -1" }}>
            <input type="checkbox" checked={f.pinned} onChange={(e) => setF({ ...f, pinned: e.target.checked })} /> Pin to the top
          </label>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Posting…" : "Post announcement"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Announcements() {
  const { can } = useAuth();
  const [tick, setTick] = useState(0);
  const [q, setQ] = useState("");
  const [composing, setComposing] = useState(false);
  const [del, setDel] = useState(null);
  const state = useLoad(async () => {
    const rows = await api("/announcements");
    api("/announcements/read-all", { method: "POST" }).catch(() => {}); // opening the page marks them read
    return rows;
  }, [tick]);
  const refresh = () => setTick((t) => t + 1);
  const manage = can("announcements.manage");
  return (
    <>
      <PageHead title="Announcements" sub="Notices from the school office">
        {manage && <button className="btn" onClick={() => setComposing(true)}><Plus size={16} /> New announcement</button>}
      </PageHead>
      {composing && <Composer onClose={() => setComposing(false)} onDone={refresh} />}
      {del && <Confirm title="Delete announcement" message={`Delete "${del.title}" for everyone?`} onClose={() => setDel(null)}
        onConfirm={async () => { await api(`/announcements/${del.id}`, { method: "DELETE" }); refresh(); }} />}
      <div className="search" style={{ marginBottom: 14 }}>
        <Search size={16} />
        <input placeholder="Search announcements…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Async state={state}>
        {(rows) => {
          const shown = q
            ? rows.filter((a) =>
                a.title.toLowerCase().includes(q.toLowerCase()) ||
                a.body.toLowerCase().includes(q.toLowerCase()))
            : rows;
          return (
          <div className="stack">
            {shown.map((a) => (
              <article key={a.id} className={`card notice ${a.pinned ? "pinned" : ""}`}>
                <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                    <span className="stat-icon amber" style={{ flexShrink: 0 }}><Megaphone size={18} /></span>
                    <div>
                      <h2 style={{ margin: 0 }}>{a.title}</h2>
                      <div className="small muted">
                        {a.author} · {new Date(a.at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
                      </div>
                    </div>
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    {a.pinned && <Badge kind="warn"><Pin size={11} /> Pinned</Badge>}
                    <Badge>{a.audience === "class" ? gradeLabel(a.grade) : WHO[a.audience]}</Badge>
                    {a.can_delete && (
                      <>
                        <button className="icon-btn" title={a.pinned ? "Unpin" : "Pin"} aria-label={a.pinned ? "Unpin" : "Pin"}
                          onClick={async () => { await api(`/announcements/${a.id}/pin?pinned=${!a.pinned}`, { method: "PUT" }); refresh(); }}>
                          {a.pinned ? <PinOff size={16} /> : <Pin size={16} />}
                        </button>
                        <button className="icon-btn" title="Delete" aria-label="Delete" onClick={() => setDel(a)}><Trash2 size={16} /></button>
                      </>
                    )}
                  </div>
                </div>
                <p className="notice-body">{a.body}</p>
              </article>
            ))}
            {rows.length > 0 && shown.length === 0 && <div className="card empty">No announcements match "{q}".</div>}
            {rows.length === 0 && <div className="card empty">No announcements yet.</div>}
          </div>
          );
        }}
      </Async>
    </>
  );
}
