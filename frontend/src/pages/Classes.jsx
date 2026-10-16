/**
 * Timetable — polished table UI.
 *
 * Rows: Day header → period rows (with time, subject badge, teacher link, actions).
 * Breaks (Short Break / Lunch Break) are visually distinct rows.
 * Admin/timetable.manage: add, edit, delete any row + bulk controls.
 * Teachers receive in-app DMs when their assignment changes (handled backend).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Clock, Copy, Database, Eraser, Pencil, Plus, Trash2, User as UserIcon, Zap } from "lucide-react";
import { api, GRADES, gradeLabel } from "../api.js";
import { SECTIONS } from "../forms.js";
import { useAuth } from "../auth.jsx";
import { Confirm, Modal, PageHead } from "../components/ui.jsx";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_FULL = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday" };

// Stable subject → colour mapping (cycles through a palette)
const PALETTE = [
  "#ede9fe", "#dbeafe", "#dcfce7", "#fef3c7", "#ffe4e6", "#e0f2fe",
  "#f3e8ff", "#d1fae5", "#fde68a", "#fed7aa",
];
const _colCache = {};
function subjectColor(name) {
  if (!_colCache[name]) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % PALETTE.length;
    _colCache[name] = PALETTE[h];
  }
  return _colCache[name];
}

// ── main ──────────────────────────────────────────────────────────────────────
export default function Classes() {
  const { can, role } = useAuth();
  const canManage = role === "admin" || can("timetable.manage");

  const [grade,   setGradeRaw] = useState("1");
  const [section, setSection]  = useState("A");

  const [rows,   setRows]  = useState([]);
  const [meta,   setMeta]  = useState(null);
  const [ttErr,  setTtErr] = useState("");
  const [ttBusy, setTtBusy] = useState(true);
  const [tick,   setTick]  = useState(0);
  const reload = () => setTick((t) => t + 1);

  const [dlg, setDlg] = useState(null);
  const [seedBusy, setSeedBusy] = useState(false);
  const [seedMsg,  setSeedMsg]  = useState("");

  // load meta once
  useEffect(() => {
    api("/timetable/meta").then(setMeta).catch(() => {});
  }, []);

  // load timetable when grade/section/tick changes
  useEffect(() => {
    setTtBusy(true); setTtErr("");
    api(`/timetable?grade=${grade}&section=${section}`)
      .then((d) => { setRows(d ?? []); setTtBusy(false); })
      .catch((e) => { setTtErr(e.message); setTtBusy(false); });
  }, [grade, section, tick]);

  function setGrade(g) {
    setGradeRaw(g);
    // reset to first available section for this grade
    const secs = (meta?.sections_by_grade?.[g] ?? []);
    if (secs.length && !secs.includes(section)) setSection(secs[0]);
  }

  const gradeSubjects = meta?.subjects_by_grade?.[grade] ?? [];
  const allStaff      = meta?.staff ?? [];
  const sections = ((meta?.sections_by_grade?.[grade] ?? []).length > 0)
    ? meta.sections_by_grade[grade]
    : ["A", "B", "C", "D"];

  // group rows by day, then sort by period_number
  const byDay = {};
  for (const d of DAYS) byDay[d] = [];
  for (const r of rows) {
    if (byDay[r.day_of_week]) byDay[r.day_of_week].push(r);
  }
  for (const d of DAYS) {
    byDay[d].sort((a, b) => {
      const ta = a.start_time ?? "99:99";
      const tb = b.start_time ?? "99:99";
      return ta < tb ? -1 : ta > tb ? 1 : a.period_number - b.period_number;
    });
  }
  const activeDays = DAYS.filter((d) => byDay[d].length > 0);

  // ── actions ──────────────────────────────────────────────────────────────
  async function saveRow(body) {
    if (dlg.type === "add") await api("/timetable", { method: "POST", body });
    else await api(`/timetable/${dlg.row.id}`, { method: "PUT", body });
    reload(); setDlg(null);
  }
  async function delRow() {
    await api(`/timetable/${dlg.row.id}`, { method: "DELETE" });
    reload(); setDlg(null);
  }
  async function clearDay(day) {
    await api("/timetable/clear", { method: "POST", body: { grade, section, day_of_week: day } });
    reload(); setDlg(null);
  }
  async function clearAll() {
    await api("/timetable/clear", { method: "POST", body: { grade, section } });
    reload(); setDlg(null);
  }
  async function fillBlank(periodCount) {
    const existing = new Set(rows.map((r) => `${r.day_of_week}:${r.period_number}`));
    const toAdd = [];
    for (const day of DAYS)
      for (let pn = 1; pn <= periodCount; pn++)
        if (!existing.has(`${day}:${pn}`))
          toAdd.push({ grade, section, day_of_week: day, period_number: pn,
            start_time: null, end_time: null, subject_id: null, staff_id: null, label: null });
    if (!toAdd.length) return;
    await api("/timetable/bulk", { method: "POST", body: { periods: toAdd } });
    reload(); setDlg(null);
  }
  async function seedDemo() {
    setSeedBusy(true); setSeedMsg("");
    try {
      const r = await api("/timetable/seed-demo", { method: "POST" });
      setSeedMsg(`✓ Created ${r.subjects_created} subject(s) and ${r.periods_created + r.periods_replaced} period rows across ${r.grades} grades × ${r.sections} sections.`);
      reload();
    } catch (e) { setSeedMsg(`Error: ${e.message}`); }
    finally { setSeedBusy(false); }
  }

  return (
    <>
      <PageHead title="Class Timetable" sub="Weekly schedule — subjects, teachers and timings for each class and section." />

      {/* ── grade selector ────────────────────────────────────────────── */}
      <div className="small muted" style={{ marginBottom: 6, fontWeight: 600 }}>Class</div>
      <div className="tabs" style={{ marginBottom: 20, flexWrap: "wrap" }}>
        {GRADES.map((g) => (
          <button key={g} className={g === grade ? "on" : ""} onClick={() => setGrade(g)}>
            {gradeLabel(g)}
          </button>
        ))}
      </div>

      {/* ── section selector ──────────────────────────────────────────── */}
      <div className="small muted" style={{ marginBottom: 6, fontWeight: 600 }}>Section</div>
      <div className="tabs" style={{ marginBottom: 20 }}>
        {sections.map((s) => (
          <button key={s} className={s === section ? "on" : ""} onClick={() => setSection(s)}>
            Section {s}
          </button>
        ))}
      </div>

      {/* ── owner toolbar ─────────────────────────────────────────────── */}
      {canManage && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20, alignItems: "center" }}>
          <button className="btn sm" onClick={() => setDlg({ type: "add" })}>
            <Plus size={14} /> Add period
          </button>
          <button className="btn ghost sm" onClick={() => setDlg({ type: "fill" })}>
            <Zap size={14} /> Fill blank slots
          </button>
          <button className="btn ghost sm" onClick={() => setDlg({ type: "copy" })}>
            <Copy size={14} /> Copy to section
          </button>
          <button className="btn ghost sm" style={{ color: "var(--bad)", borderColor: "var(--bad)" }}
            onClick={() => setDlg({ type: "clearAll" })}>
            <Eraser size={14} /> Clear {gradeLabel(grade)}-{section}
          </button>
          <span style={{ flex: 1 }} />
          <button className="btn ghost sm" onClick={() => setDlg({ type: "seed" })} disabled={seedBusy}>
            <Database size={14} /> {seedBusy ? "Seeding…" : "Load demo timetable"}
          </button>
        </div>
      )}
      {seedMsg && (
        <div className={seedMsg.startsWith("✓") ? "notice" : "error"} style={{ marginBottom: 16 }}>
          {seedMsg}
        </div>
      )}

      {/* ── timetable ─────────────────────────────────────────────────── */}
      {ttBusy && <div className="empty">Loading…</div>}
      {ttErr  && <div className="error">{ttErr}</div>}

      {!ttBusy && !ttErr && rows.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "40px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 10 }}>📅</div>
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>
            No timetable yet for {gradeLabel(grade)}-{section}
          </div>
          <div className="muted" style={{ marginBottom: 20, maxWidth: 440, margin: "0 auto 20px" }}>
            {canManage
              ? <>Click <b>Load demo timetable</b> to populate all grades with a realistic schedule, or use <b>Add period</b> to build it manually.</>
              : "The timetable for this class has not been set up yet. Contact the school admin."}
          </div>
          {canManage && (
            <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
              <button className="btn" onClick={() => setDlg({ type: "seed" })} disabled={seedBusy}>
                <Database size={15} /> {seedBusy ? "Seeding…" : "Load demo timetable"}
              </button>
              <button className="btn ghost" onClick={() => setDlg({ type: "add" })}>
                <Plus size={15} /> Add period manually
              </button>
            </div>
          )}
        </div>
      )}

      {!ttBusy && !ttErr && rows.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {(activeDays.length > 0 ? activeDays : DAYS).map((day) => (
            <DayCard
              key={day}
              day={day}
              periods={byDay[day]}
              canManage={canManage}
              onAdd={() => setDlg({ type: "add", defaultDay: day })}
              onEdit={(row) => setDlg({ type: "edit", row })}
              onDel={(row) => setDlg({ type: "del", row })}
              onClearDay={() => setDlg({ type: "clearDay", day })}
            />
          ))}
        </div>
      )}

      {/* ── dialogs ───────────────────────────────────────────────────── */}
      {(dlg?.type === "add" || dlg?.type === "edit") && (
        <RowModal
          title={dlg.type === "add" ? `Add period — ${gradeLabel(grade)}-${section}` : "Edit period"}
          grade={grade} section={section}
          initial={dlg.row ?? (dlg.defaultDay ? { day_of_week: dlg.defaultDay } : null)}
          subjects={gradeSubjects} staff={allStaff}
          onClose={() => setDlg(null)} onSave={saveRow}
        />
      )}
      {dlg?.type === "del" && (
        <Confirm title="Delete period"
          message={`Delete ${dlg.row.label ?? `period ${dlg.row.period_number}`} on ${DAY_FULL[dlg.row.day_of_week]}${dlg.row.subject_name ? ` (${dlg.row.subject_name})` : ""}?`}
          onClose={() => setDlg(null)} onConfirm={delRow} />
      )}
      {dlg?.type === "clearDay" && (
        <Confirm title={`Clear ${DAY_FULL[dlg.day]}`}
          message={`Delete all ${byDay[dlg.day]?.length ?? 0} entries on ${DAY_FULL[dlg.day]} for ${gradeLabel(grade)}-${section}?`}
          onClose={() => setDlg(null)} onConfirm={() => clearDay(dlg.day)} />
      )}
      {dlg?.type === "clearAll" && (
        <Confirm title={`Clear ${gradeLabel(grade)}-${section}`}
          message={`Permanently delete all ${rows.length} entries for ${gradeLabel(grade)}-${section}?`}
          onClose={() => setDlg(null)} onConfirm={clearAll} />
      )}
      {dlg?.type === "fill" && (
        <FillModal grade={grade} section={section} existing={rows.length}
          onClose={() => setDlg(null)} onFill={fillBlank} />
      )}
      {dlg?.type === "copy" && (
        <CopyModal fromGrade={grade} fromSection={section}
          onClose={() => setDlg(null)}
          onCopy={async (body) => { await api("/timetable/copy", { method: "POST", body }); reload(); setDlg(null); }} />
      )}
      {dlg?.type === "seed" && (
        <SeedModal onClose={() => setDlg(null)} onSeed={async () => { await seedDemo(); setDlg(null); }} busy={seedBusy} />
      )}
    </>
  );
}

// ── Day card ──────────────────────────────────────────────────────────────────
function DayCard({ day, periods, canManage, onAdd, onEdit, onDel, onClearDay }) {
  return (
    <div className="card flush">
      {/* Day header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", background: "var(--primary-soft)",
        borderBottom: "1px solid var(--border)",
      }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: "var(--primary)" }}>
          {DAY_FULL[day]}
        </span>
        {canManage && (
          <div style={{ display: "flex", gap: 4 }}>
            <button className="btn ghost sm" style={{ fontSize: 12 }} onClick={onAdd}>
              <Plus size={12} /> Add
            </button>
            <button className="icon-btn danger" title={`Clear ${DAY_FULL[day]}`} onClick={onClearDay}>
              <Eraser size={13} />
            </button>
          </div>
        )}
      </div>

      {/* Period rows */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <Th w={50}>#</Th>
            <Th w={120}><Clock size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />Time</Th>
            <Th><BookOpen size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />Subject</Th>
            <Th><UserIcon size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />Teacher</Th>
            {canManage && <Th w={80} />}
          </tr>
        </thead>
        <tbody>
          {periods.length === 0 && (
            <tr><td colSpan={canManage ? 5 : 4} style={{ ...td, color: "var(--muted)", fontStyle: "italic" }}>No periods — click Add to create one.</td></tr>
          )}
          {periods.map((r) => <PeriodRow key={r.id} row={r} canManage={canManage} onEdit={onEdit} onDel={onDel} />)}
        </tbody>
      </table>
    </div>
  );
}

// ── Period row ────────────────────────────────────────────────────────────────
function PeriodRow({ row: r, canManage, onEdit, onDel }) {
  const isBreak = !!r.label;
  const breakStyle = r.label?.toLowerCase().includes("lunch")
    ? { background: "#f0fdf4", borderLeft: "3px solid #16a34a" }
    : isBreak
      ? { background: "#fffbeb", borderLeft: "3px solid #f59e0b" }
      : {};

  return (
    <tr style={{ borderBottom: "1px solid var(--border)", ...breakStyle }}>
      {/* Period number */}
      <td style={{ ...td, textAlign: "center", fontWeight: 700, color: "var(--muted)", fontSize: 13, width: 50 }}>
        {isBreak ? "—" : r.period_number}
      </td>

      {/* Time */}
      <td style={{ ...td, whiteSpace: "nowrap", width: 120 }}>
        {r.start_time ? (
          <span style={{ fontWeight: 600, fontSize: 13 }}>
            {r.start_time}
            {r.end_time && <span style={{ color: "var(--muted)", fontWeight: 400 }}> – {r.end_time}</span>}
          </span>
        ) : <span style={{ color: "#c9cfe0" }}>—</span>}
      </td>

      {/* Subject / Label */}
      <td style={{ ...td }}>
        {isBreak ? (
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 13,
            color: r.label.toLowerCase().includes("lunch") ? "#15803d" : "#b45309",
          }}>
            {r.label.toLowerCase().includes("lunch") ? "🍱" : "☕"} {r.label}
          </span>
        ) : r.subject_id ? (
          <Link to={`/subjects/${r.subject_id}`}
            style={{ textDecoration: "none" }}>
            <span style={{
              display: "inline-block", padding: "3px 10px", borderRadius: 8,
              background: subjectColor(r.subject_name),
              fontWeight: 600, fontSize: 13, color: "#1e293b",
            }}>
              {r.subject_name}
            </span>
          </Link>
        ) : (
          <span className="muted small" style={{ fontStyle: "italic" }}>Not assigned</span>
        )}
      </td>

      {/* Teacher */}
      <td style={{ ...td }}>
        {r.staff_id ? (
          <Link to={`/staff/${r.staff_id}`}
            style={{ color: "var(--text)", fontSize: 13, textDecoration: "none", fontWeight: 500 }}>
            {r.staff_name}
          </Link>
        ) : isBreak ? null : (
          <span style={{ color: "#c9cfe0", fontSize: 12 }}>Unassigned</span>
        )}
      </td>

      {/* Actions */}
      {canManage && (
        <td style={{ ...td, whiteSpace: "nowrap", width: 80 }}>
          <button className="icon-btn" title="Edit" onClick={() => onEdit(r)}><Pencil size={14} /></button>
          <button className="icon-btn danger" title="Delete" onClick={() => onDel(r)}><Trash2 size={14} /></button>
        </td>
      )}
    </tr>
  );
}

// ── Add / Edit modal ──────────────────────────────────────────────────────────
function RowModal({ title, grade, section, initial, subjects, staff, onClose, onSave }) {
  const [f, setF] = useState({
    day_of_week:   initial?.day_of_week   ?? "Mon",
    period_number: initial?.period_number ?? 1,
    start_time:    initial?.start_time    ?? "",
    end_time:      initial?.end_time      ?? "",
    subject_id:    initial?.subject_id    ? String(initial.subject_id) : "",
    staff_id:      initial?.staff_id      ? String(initial.staff_id)   : "",
    label:         initial?.label         ?? "",
  });
  const [err, setErr]   = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await onSave({
        grade, section,
        day_of_week:   f.day_of_week,
        period_number: Number(f.period_number),
        start_time:    f.start_time || null,
        end_time:      f.end_time   || null,
        subject_id:    f.subject_id ? Number(f.subject_id) : null,
        staff_id:      f.staff_id   ? Number(f.staff_id)   : null,
        label:         f.label      || null,
      });
    } catch (x) { setErr(x.message); setBusy(false); }
  }

  return (
    <Modal title={title} onClose={onClose} wide>
      <form onSubmit={submit}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          <div className="field">
            <label>Day *</label>
            <select value={f.day_of_week} onChange={(e) => setF({ ...f, day_of_week: e.target.value })}>
              {DAYS.map((d) => <option key={d} value={d}>{DAY_FULL[d]}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Period # *</label>
            <input type="number" min={1} max={20} required value={f.period_number}
              onChange={(e) => setF({ ...f, period_number: e.target.value })} />
          </div>
          <div className="field">
            <label>Start time</label>
            <input type="time" value={f.start_time} onChange={(e) => setF({ ...f, start_time: e.target.value })} />
          </div>
          <div className="field">
            <label>End time</label>
            <input type="time" value={f.end_time} onChange={(e) => setF({ ...f, end_time: e.target.value })} />
          </div>
          <div className="field">
            <label>Subject</label>
            <select value={f.subject_id} onChange={(e) => setF({ ...f, subject_id: e.target.value })}>
              <option value="">— none —</option>
              {subjects.length === 0
                ? <option disabled>No subjects yet — add them in Subjects first</option>
                : subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Teacher <span className="small muted">(notified on save)</span></label>
            <select value={f.staff_id} onChange={(e) => setF({ ...f, staff_id: e.target.value })}>
              <option value="">— none —</option>
              {staff.length === 0
                ? <option disabled>No staff yet — add them in Staff first</option>
                : staff.map((s) => <option key={s.id} value={s.id}>{s.name}{s.designation ? ` — ${s.designation}` : ""}</option>)}
            </select>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label>Label <span className="small muted">(e.g. "Short Break", "Lunch Break" — leave blank for teaching period)</span></label>
            <input maxLength={40} value={f.label} placeholder="Leave blank for a regular teaching period"
              onChange={(e) => setF({ ...f, label: e.target.value })} />
          </div>
        </div>
        <p className="small muted" style={{ margin: "10px 0 0" }}>
          The assigned teacher will receive an in-app message when you save.
        </p>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save period"}</button>
        </div>
      </form>
    </Modal>
  );
}

// ── Fill blank slots modal ────────────────────────────────────────────────────
function FillModal({ grade, section, existing, onClose, onFill }) {
  const [count, setCount] = useState(8);
  const [busy,  setBusy]  = useState(false);
  const [err,   setErr]   = useState("");
  const toCreate = Math.max(0, DAYS.length * count - existing);

  async function go() {
    setBusy(true); setErr("");
    try { await onFill(count); onClose(); }
    catch (x) { setErr(x.message); setBusy(false); }
  }

  return (
    <Modal title="Fill blank slots" onClose={onClose}>
      {err && <div className="error">{err}</div>}
      <p>Create empty period slots for <b>{gradeLabel(grade)}-{section}</b> across the whole week. Edit each cell afterwards to add subject and teacher.</p>
      <div className="field" style={{ marginBottom: 14 }}>
        <label>Periods per day</label>
        <div className="tabs" style={{ marginBottom: 0 }}>
          {[6, 7, 8, 9, 10].map((n) => (
            <button key={n} type="button" className={n === count ? "on" : ""} onClick={() => setCount(n)}>{n}</button>
          ))}
        </div>
      </div>
      <p className="small muted">Will create <b>{toCreate}</b> new slot{toCreate !== 1 ? "s" : ""} ({DAYS.length} days × {count} − {existing} existing).</p>
      {toCreate === 0 && <div className="notice">All slots already exist.</div>}
      <div className="modal-foot">
        <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn" onClick={go} disabled={busy || toCreate === 0}>
          {busy ? "Creating…" : `Create ${toCreate} slot${toCreate !== 1 ? "s" : ""}`}
        </button>
      </div>
    </Modal>
  );
}

// ── Copy to section modal ─────────────────────────────────────────────────────
function CopyModal({ fromGrade, fromSection, onClose, onCopy }) {
  const [toGrade,   setToGrade]   = useState(fromGrade);
  const [toSection, setToSection] = useState(fromSection === "A" ? "B" : "A");
  const [overwrite, setOverwrite] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err,  setErr]  = useState("");

  async function go(e) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await onCopy({ from_grade: fromGrade, from_section: fromSection, to_grade: toGrade, to_section: toSection, overwrite });
    } catch (x) { setErr(x.message); setBusy(false); }
  }

  return (
    <Modal title={`Copy — ${gradeLabel(fromGrade)}-${fromSection}`} onClose={onClose} wide>
      <form onSubmit={go}>
        {err && <div className="error">{err}</div>}
        <p className="muted" style={{ marginBottom: 14 }}>Copy the full weekly schedule to another section. Subject and teacher assignments copy as-is.</p>
        <div className="form-grid">
          <div className="field">
            <label>Target class</label>
            <select value={toGrade} onChange={(e) => setToGrade(e.target.value)}>
              {GRADES.map((g) => <option key={g} value={g}>{gradeLabel(g)}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Target section</label>
            <select value={toSection} onChange={(e) => setToSection(e.target.value)}>
              {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer", fontWeight: "normal" }}>
              <input type="checkbox" checked={overwrite} style={{ width: "auto" }} onChange={(e) => setOverwrite(e.target.checked)} />
              Replace existing periods in the target section
            </label>
          </div>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Copying…" : "Copy timetable"}</button>
        </div>
      </form>
    </Modal>
  );
}

// ── Seed demo modal ───────────────────────────────────────────────────────────
function SeedModal({ onClose, onSeed, busy }) {
  const [err, setErr] = useState("");

  async function go() {
    setErr("");
    try { await onSeed(); }
    catch (x) { setErr(x.message); }
  }

  return (
    <Modal title="Load demo timetable" onClose={onClose}>
      {err && <div className="error">{err}</div>}
      <p>This will create a complete weekly timetable for <b>all grades</b> (LKG to Class 10), sections <b>A &amp; B</b>, with:</p>
      <ul style={{ color: "var(--muted)", lineHeight: 2, paddingLeft: 20 }}>
        <li><b>8 teaching periods</b> per day (45 min each)</li>
        <li><b>Short break</b> 10:15 – 10:30</li>
        <li><b>Lunch break</b> 12:00 – 12:45</li>
        <li>Age-appropriate subjects per grade band</li>
        <li>Subjects created automatically if they don't exist</li>
        <li>Teacher assignments left blank — assign from the edit modal</li>
      </ul>
      <p className="small muted">Existing periods are replaced. This is safe to run multiple times.</p>
      <div className="modal-foot">
        <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn" onClick={go} disabled={busy}>
          <Database size={14} /> {busy ? "Creating…" : "Create demo timetable"}
        </button>
      </div>
    </Modal>
  );
}

// ── tiny helpers ──────────────────────────────────────────────────────────────
const td = { padding: "10px 14px", verticalAlign: "middle" };
function Th({ children, w }) {
  return (
    <th style={{
      padding: "8px 14px", textAlign: "left", fontSize: 11, fontWeight: 700,
      color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".07em",
      background: "#fafbfe", whiteSpace: "nowrap", width: w,
    }}>
      {children}
    </th>
  );
}
