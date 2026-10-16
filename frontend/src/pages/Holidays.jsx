import { useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Plus, Pencil, Search, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Confirm, Modal, PageHead, useLoad } from "../components/ui.jsx";

const MONTHS = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"];
const CATEGORY_COLOR = {
  national: "#e11d48",
  regional: "#f59e0b",
  school: "#5b4bdb",
};
const CATEGORIES = ["national", "regional", "school"];
const CATEGORY_LABEL = { national: "National", regional: "Regional", school: "School" };

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}
function firstDayOfMonth(year, month) {
  // 0=Sun,1=Mon…6=Sat → shift so Monday=0
  return (new Date(year, month, 1).getDay() + 6) % 7;
}

function HolidayForm({ holiday, onClose, onSaved }) {
  const [f, setF] = useState({
    date: holiday?.date ?? new Date().toISOString().slice(0, 10),
    name: holiday?.name ?? "",
    description: holiday?.description ?? "",
    category: holiday?.category ?? "school",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      if (holiday) {
        await api(`/holidays/${holiday.id}`, { method: "PUT", body: f });
      } else {
        await api("/holidays", { method: "POST", body: f });
      }
      onSaved();
      onClose();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={holiday ? "Edit holiday" : "Add holiday"} onClose={onClose}>
      <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          <div className="field">
            <label>Date *</label>
            <input type="date" required value={f.date}
              onChange={(e) => setF({ ...f, date: e.target.value })} />
          </div>
          <div className="field">
            <label>Category *</label>
            <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Name *</label>
          <input required maxLength={120} value={f.name} placeholder="e.g. Diwali, Independence Day"
            onChange={(e) => setF({ ...f, name: e.target.value })} />
        </div>
        <div className="field">
          <label>Description (optional)</label>
          <textarea rows={2} maxLength={300} value={f.description}
            onChange={(e) => setF({ ...f, description: e.target.value })} />
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : holiday ? "Save" : "Add holiday"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Holidays() {
  const { can, session } = useAuth();
  const canManage = session?.role === "admin" || can("holidays.manage");
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [q, setQ] = useState("");
  const [dlg, setDlg] = useState(null);
  const [tick, setTick] = useState(0);
  const state = useLoad(() => api(`/holidays?year=${year}`), [year, tick]);
  const reload = () => setTick((t) => t + 1);

  const prevMonth = () => {
    if (month === 0) { setYear(year - 1); setMonth(11); }
    else setMonth(month - 1);
  };
  const nextMonth = () => {
    if (month === 11) { setYear(year + 1); setMonth(0); }
    else setMonth(month + 1);
  };

  return (
    <>
      <PageHead title="Holiday Calendar" sub="School holidays and non-working days for all members">
        {canManage && (
          <button className="btn" onClick={() => setDlg({ type: "add" })}>
            <Plus size={16} /> Add holiday
          </button>
        )}
      </PageHead>

      <Async state={state}>
        {(allHolidays) => {
          // Filter to current month
          const monthStr = `${year}-${String(month + 1).padStart(2, "0")}`;
          const monthHolidays = allHolidays.filter((h) => h.date.startsWith(monthStr));
          // Build calendar grid
          const days = daysInMonth(year, month);
          const offset = firstDayOfMonth(year, month);
          const todayStr = today.toISOString().slice(0, 10);

          // Map date → holiday
          const holidayMap = {};
          for (const h of monthHolidays) {
            const d = parseInt(h.date.slice(8));
            holidayMap[d] = h;
          }

          return (
            <div className="grid g2" style={{ alignItems: "start" }}>
              {/* ── Calendar ─────────────────────────────────────────────── */}
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 12, alignItems: "center" }}>
                  <button className="icon-btn" onClick={prevMonth}><ChevronLeft size={18} /></button>
                  <h2 style={{ margin: 0 }}>{MONTHS[month]} {year}</h2>
                  <button className="icon-btn" onClick={nextMonth}><ChevronRight size={18} /></button>
                </div>
                {/* Day headers */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 4 }}>
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
                    <div key={d} style={{ textAlign: "center", fontSize: 11, fontWeight: 700, color: "var(--muted)", padding: "4px 0" }}>{d}</div>
                  ))}
                </div>
                {/* Day cells */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
                  {Array.from({ length: offset }, (_, i) => <div key={`e${i}`} />)}
                  {Array.from({ length: days }, (_, i) => {
                    const d = i + 1;
                    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
                    const h = holidayMap[d];
                    const isToday = dateStr === todayStr;
                    return (
                      <div key={d}
                        title={h?.name}
                        style={{
                          textAlign: "center",
                          padding: "6px 2px",
                          borderRadius: 8,
                          fontSize: 13,
                          fontWeight: isToday ? 800 : 400,
                          background: h ? (CATEGORY_COLOR[h.category] + "22") : isToday ? "var(--primary-soft, #eef2ff)" : "transparent",
                          border: isToday ? "2px solid var(--primary, #5b4bdb)" : h ? `1px solid ${CATEGORY_COLOR[h.category]}44` : "1px solid transparent",
                          color: h ? CATEGORY_COLOR[h.category] : "inherit",
                          cursor: (h && canManage) ? "pointer" : "default",
                        }}
                        onClick={() => h && canManage && setDlg({ type: "edit", holiday: h })}
                      >
                        <div>{d}</div>
                        {h && <div style={{ fontSize: 9, lineHeight: 1.2, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.name}</div>}
                      </div>
                    );
                  })}
                </div>
                {/* Legend */}
                <div className="row" style={{ marginTop: 14, gap: 14, flexWrap: "wrap" }}>
                  {CATEGORIES.map((c) => (
                    <div key={c} className="row" style={{ gap: 6, fontSize: 12 }}>
                      <span style={{ width: 12, height: 12, borderRadius: 3, background: CATEGORY_COLOR[c], display: "inline-block" }} />
                      {CATEGORY_LABEL[c]}
                    </div>
                  ))}
                </div>
              </div>

              {/* ── Holiday list for this month ───────────────────────────── */}
              <div>
                <div className="card" style={{ marginBottom: 12 }}>
                  <h3 style={{ marginTop: 0 }}>
                    {MONTHS[month]} {year} · {monthHolidays.length} holiday{monthHolidays.length !== 1 ? "s" : ""}
                  </h3>
                  {monthHolidays.length === 0 && (
                    <div className="muted">No holidays in this month.</div>
                  )}
                  {monthHolidays.map((h) => (
                    <div key={h.id} className="row" style={{ justifyContent: "space-between", marginBottom: 10, alignItems: "flex-start" }}>
                      <div className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                        <div className="timeline-date" style={{ minWidth: 44, background: CATEGORY_COLOR[h.category] + "22", color: CATEGORY_COLOR[h.category] }}>
                          {h.date.slice(8)}<br /><span style={{ fontSize: 9 }}>{MONTHS[parseInt(h.date.slice(5, 7)) - 1].slice(0, 3)}</span>
                        </div>
                        <div>
                          <b>{h.name}</b>
                          <div style={{ fontSize: 12, color: CATEGORY_COLOR[h.category] }}>{CATEGORY_LABEL[h.category]}</div>
                          {h.description && <div className="small muted">{h.description}</div>}
                        </div>
                      </div>
                      {canManage && (
                        <div className="row" style={{ gap: 4 }}>
                          <button className="icon-btn" title="Edit" onClick={() => setDlg({ type: "edit", holiday: h })}><Pencil size={14} /></button>
                          <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", holiday: h })}><Trash2 size={14} /></button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Full year list */}
                <div className="card">
                  <div className="row" style={{ justifyContent: "space-between", marginBottom: 12, alignItems: "center" }}>
                    <h3 style={{ margin: 0 }}>All holidays in {year}</h3>
                  </div>
                  <div className="search" style={{ marginBottom: 10 }}>
                    <Search size={15} />
                    <input placeholder="Search holidays…" value={q} onChange={(e) => setQ(e.target.value)} />
                  </div>
                  {allHolidays.length === 0 && <div className="muted">No holidays added yet for {year}.</div>}
                  {allHolidays.length > 0 && q && allHolidays.filter((h) => h.name.toLowerCase().includes(q.toLowerCase())).length === 0 && (
                    <div className="muted">No holidays match "{q}".</div>
                  )}
                  {allHolidays.filter((h) => !q || h.name.toLowerCase().includes(q.toLowerCase())).map((h) => (
                    <div key={h.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                      <div>
                        <b style={{ fontSize: 13 }}>{h.name}</b>
                        <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>{h.date}</span>
                      </div>
                      <span style={{ fontSize: 11, color: CATEGORY_COLOR[h.category], fontWeight: 600 }}>
                        {CATEGORY_LABEL[h.category]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        }}
      </Async>

      {dlg?.type === "add" && (
        <HolidayForm onClose={() => setDlg(null)} onSaved={reload} />
      )}
      {dlg?.type === "edit" && (
        <HolidayForm holiday={dlg.holiday} onClose={() => setDlg(null)} onSaved={reload} />
      )}
      {dlg?.type === "del" && (
        <Confirm title="Delete holiday" message={`Delete "${dlg.holiday.name}" (${dlg.holiday.date})?`}
          onClose={() => setDlg(null)}
          onConfirm={async () => { await api(`/holidays/${dlg.holiday.id}`, { method: "DELETE" }); reload(); }} />
      )}
    </>
  );
}
