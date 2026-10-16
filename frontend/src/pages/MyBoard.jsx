/**
 * MyBoard — personal board for every user (staff, admin, student).
 *
 * Left column (2/3 width on wide screens):
 *   • For staff: Today's schedule, Subjects & marks stats, Weekly schedule
 *   • For students: quick links to own profile / marks / attendance
 *   • For admin: quick stat links
 *
 * Right column (1/3 width):
 *   • Sticky notes (private, only visible to the note owner)
 *     - Handwritten Caveat font
 *     - 8 sticky background colours + 9 text colours
 *     - Bold / Italic toggles
 *     - Inline editing (click to edit, auto-save on blur / Enter)
 *     - Pin indicator
 *
 * Bottom:
 *   • Recent announcements
 *   • Upcoming holidays
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bell, Bold, BookOpen, CalendarCheck, CalendarClock, CalendarRange,
  ClipboardList, Italic, Megaphone, MessagesSquare, Plus,
  Star, Trash2, Users, X,
} from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, PageHead, Photo, Stat, tone, useLoad } from "../components/ui.jsx";

// ── colour palettes ───────────────────────────────────────────────────────────
const NOTE_COLORS = [
  { hex: "#fef08a", label: "Yellow" },
  { hex: "#bbf7d0", label: "Mint" },
  { hex: "#bfdbfe", label: "Blue" },
  { hex: "#fed7aa", label: "Peach" },
  { hex: "#f5d0fe", label: "Lilac" },
  { hex: "#fecaca", label: "Pink" },
  { hex: "#e0f2fe", label: "Sky" },
  { hex: "#ffffff", label: "White" },
];
const TEXT_COLORS = [
  { hex: "#1f2328", label: "Black" },
  { hex: "#5b4bdb", label: "Indigo" },
  { hex: "#16a34a", label: "Green" },
  { hex: "#e11d48", label: "Red" },
  { hex: "#d97706", label: "Amber" },
  { hex: "#0284c7", label: "Blue" },
  { hex: "#9333ea", label: "Purple" },
  { hex: "#374151", label: "Dark" },
  { hex: "#ffffff", label: "White" },
];

// ── Sticky note component ─────────────────────────────────────────────────────
function StickyNote({ note, onSave, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(note.text);
  const [noteColor, setNoteColor] = useState(note.note_color);
  const [textColor, setTextColor] = useState(note.text_color);
  const [bold, setBold] = useState(note.bold);
  const [italic, setItalic] = useState(note.italic);
  const [busy, setBusy] = useState(false);
  const textRef = useRef(null);

  useEffect(() => {
    if (editing && textRef.current) textRef.current.focus();
  }, [editing]);

  async function save() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await onSave(note.id, { text, note_color: noteColor, text_color: textColor, bold, italic });
    } finally {
      setBusy(false);
      setEditing(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Escape") { setEditing(false); setText(note.text); }
    if (e.key === "Enter" && e.ctrlKey) save();
  }

  return (
    <div
      className="sticky"
      style={{ background: noteColor }}
    >
      <div className="sticky-pin" />

      {editing ? (
        <>
          {/* Toolbar when editing */}
          <div className="sticky-toolbar">
            {NOTE_COLORS.map((c) => (
              <button
                key={c.hex}
                className={`color-swatch${noteColor === c.hex ? " selected" : ""}`}
                title={c.label}
                style={{ background: c.hex, border: "2px solid " + (noteColor === c.hex ? "#374151" : "rgba(0,0,0,.15)") }}
                onClick={() => setNoteColor(c.hex)}
              />
            ))}
            <div style={{ width: 1, height: 20, background: "rgba(0,0,0,.15)", margin: "0 2px" }} />
            {TEXT_COLORS.map((c) => (
              <button
                key={c.hex}
                className={`color-swatch${textColor === c.hex ? " selected" : ""}`}
                title={`Text: ${c.label}`}
                style={{
                  background: c.hex,
                  border: "2px solid " + (textColor === c.hex ? "#374151" : "rgba(0,0,0,.15)"),
                  boxShadow: c.hex === "#ffffff" ? "0 0 0 1px #ccc" : "none",
                }}
                onClick={() => setTextColor(c.hex)}
              />
            ))}
            <div style={{ width: 1, height: 20, background: "rgba(0,0,0,.15)", margin: "0 2px" }} />
            <button
              title="Bold"
              onClick={() => setBold(!bold)}
              style={{
                border: "1.5px solid rgba(0,0,0,.2)", borderRadius: 6, padding: "2px 6px",
                background: bold ? "rgba(0,0,0,.18)" : "rgba(255,255,255,.5)",
                cursor: "pointer", fontFamily: "inherit", fontWeight: 700,
              }}
            >
              <Bold size={13} />
            </button>
            <button
              title="Italic"
              onClick={() => setItalic(!italic)}
              style={{
                border: "1.5px solid rgba(0,0,0,.2)", borderRadius: 6, padding: "2px 6px",
                background: italic ? "rgba(0,0,0,.18)" : "rgba(255,255,255,.5)",
                cursor: "pointer", fontFamily: "inherit",
              }}
            >
              <Italic size={13} />
            </button>
          </div>

          <textarea
            ref={textRef}
            className="sticky-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={1000}
            rows={5}
            style={{
              color: textColor,
              fontWeight: bold ? 700 : 400,
              fontStyle: italic ? "italic" : "normal",
              background: noteColor,
            }}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 8, justifyContent: "flex-end" }}>
            <button className="btn ghost sm" onClick={() => { setEditing(false); setText(note.text); }}>
              <X size={12} /> Cancel
            </button>
            <button className="btn sm" onClick={save} disabled={busy || !text.trim()}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p
            className="sticky-text"
            style={{
              color: textColor,
              fontWeight: bold ? 700 : 400,
              fontStyle: italic ? "italic" : "normal",
              cursor: "pointer",
            }}
            onClick={() => setEditing(true)}
            title="Click to edit"
          >
            {note.text}
          </p>
          <div className="sticky-meta">
            {note.updated_at
              ? `edited ${note.updated_at.slice(0, 10)}`
              : note.created_at.slice(0, 10)}
          </div>
          <div className="sticky-actions">
            <button title="Edit" onClick={() => setEditing(true)}
              style={{ color: textColor }}><Bold size={12} /></button>
            <button title="Delete" onClick={() => onDelete(note.id)}
              style={{ color: "#e11d48" }}><Trash2 size={12} /></button>
          </div>
        </>
      )}
    </div>
  );
}

// ── New note composer ─────────────────────────────────────────────────────────
function NoteComposer({ onCreate }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [noteColor, setNoteColor] = useState("#fef08a");
  const [textColor, setTextColor] = useState("#1f2328");
  const [bold, setBold] = useState(false);
  const [italic, setItalic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true); setErr("");
    try {
      await onCreate({ text, note_color: noteColor, text_color: textColor, bold, italic });
      setText(""); setOpen(false);
    } catch (x) { setErr(x.message); }
    finally { setBusy(false); }
  }

  if (!open) {
    return (
      <button className="sticky-new-btn" onClick={() => setOpen(true)}>
        <Plus size={18} /> Write a new note…
      </button>
    );
  }

  return (
    <div className="sticky-composer">
      {err && <div className="error" style={{ marginBottom: 8 }}>{err}</div>}
      <div className="sticky-toolbar">
        <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "Inter,system-ui,sans-serif", marginRight: 4 }}>Sticky:</span>
        {NOTE_COLORS.map((c) => (
          <button
            key={c.hex}
            type="button"
            className={`color-swatch${noteColor === c.hex ? " selected" : ""}`}
            title={c.label}
            style={{ background: c.hex, border: "2px solid " + (noteColor === c.hex ? "#374151" : "rgba(0,0,0,.15)") }}
            onClick={() => setNoteColor(c.hex)}
          />
        ))}
        <div style={{ width: 1, height: 20, background: "rgba(0,0,0,.15)", margin: "0 4px" }} />
        <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "Inter,system-ui,sans-serif", marginRight: 4 }}>Text:</span>
        {TEXT_COLORS.map((c) => (
          <button
            key={c.hex}
            type="button"
            className={`color-swatch${textColor === c.hex ? " selected" : ""}`}
            title={`Text: ${c.label}`}
            style={{ background: c.hex, border: "2px solid " + (textColor === c.hex ? "#374151" : "rgba(0,0,0,.15)"), boxShadow: c.hex === "#ffffff" ? "0 0 0 1px #ccc" : "none" }}
            onClick={() => setTextColor(c.hex)}
          />
        ))}
        <div style={{ width: 1, height: 20, background: "rgba(0,0,0,.15)", margin: "0 4px" }} />
        <button type="button" title="Bold"
          onClick={() => setBold(!bold)}
          style={{ border: "1.5px solid rgba(0,0,0,.2)", borderRadius: 6, padding: "2px 6px", background: bold ? "rgba(0,0,0,.12)" : "#fff", cursor: "pointer" }}>
          <Bold size={13} />
        </button>
        <button type="button" title="Italic"
          onClick={() => setItalic(!italic)}
          style={{ border: "1.5px solid rgba(0,0,0,.2)", borderRadius: 6, padding: "2px 6px", background: italic ? "rgba(0,0,0,.12)" : "#fff", cursor: "pointer" }}>
          <Italic size={13} />
        </button>
      </div>
      <form onSubmit={submit}>
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={1000}
          rows={4}
          placeholder="Write something…"
          style={{
            width: "100%", fontFamily: '"Caveat","Comic Sans MS",cursive',
            fontSize: 22, lineHeight: 1.3, padding: "10px 12px",
            borderRadius: 10, border: "1.5px solid var(--border)",
            background: noteColor, color: textColor,
            fontWeight: bold ? 700 : 400, fontStyle: italic ? "italic" : "normal",
            resize: "vertical", outline: "none",
          }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8, justifyContent: "flex-end" }}>
          <button type="button" className="btn ghost sm" onClick={() => setOpen(false)}>Cancel</button>
          <button type="submit" className="btn sm" disabled={busy || !text.trim()}>
            {busy ? "Pinning…" : "Pin note"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Staff dashboard widgets ───────────────────────────────────────────────────
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_FULL = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday" };
const STATUS_KIND = { pending: "warn", approved: "good", rejected: "bad" };

function PeriodPill({ p }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "8px 12px", borderRadius: 8, flex: "1 1 180px",
      background: "var(--surface)", border: "1px solid var(--border)",
    }}>
      <div style={{ textAlign: "center", minWidth: 30 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--primary)" }}>P{p.period_number}</div>
        {p.start_time && <div style={{ fontSize: 10, color: "var(--muted)" }}>{p.start_time}</div>}
      </div>
      <div>
        <div style={{ fontWeight: 600, fontSize: 13 }}>
          {p.subject_name || <span style={{ color: "var(--muted)", fontWeight: 400 }}>—</span>}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>
          {p.grade}-{p.section}{p.start_time && p.end_time ? ` · ${p.start_time}–${p.end_time}` : ""}
        </div>
      </div>
    </div>
  );
}

function StaffWidgets({ d }) {
  const activeDays = DAYS.filter((day) => (d.week_schedule[day] ?? []).length > 0);
  const s = d.staff;

  return (
    <>
      {/* Profile strip */}
      <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <Photo kind="staff" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} size={56} />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontSize: "1.1rem" }}>{s.name}</b>
            {s.class_teacher_of && (
              <span className="chip" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <Star size={10} /> Class Head · {s.class_teacher_of}
              </span>
            )}
          </div>
          <div className="muted small">{s.designation} · {s.department}</div>
          {d.classes_taught.length > 0 && (
            <div className="chip-list" style={{ marginTop: 4 }}>
              {d.classes_taught.map((c) => (
                <span key={`${c.grade}${c.section}`} className="chip">
                  Class {c.grade}-{c.section}
                </span>
              ))}
            </div>
          )}
        </div>
        <Link to={`/staff/${s.id}`} className="btn ghost sm">Full profile</Link>
      </div>

      {/* Quick stats */}
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat icon={CalendarClock} tint="indigo" label="Periods/week"
          value={activeDays.reduce((n, day) => n + (d.week_schedule[day]?.length ?? 0), 0)}
          sub={`${activeDays.length} day${activeDays.length !== 1 ? "s" : ""}`} to="/classes" />
        <Stat icon={MessagesSquare} tint="sky" label="Unread msgs"
          value={d.unread_messages || "0"} sub="Messages" to="/messages" />
        <Stat icon={ClipboardList} tint="amber" label="Pending leaves"
          value={d.pending_leaves || "0"}
          sub={d.reviewer_pending > 0 ? `${d.reviewer_pending} to review` : "No pending"} to="/leaves" />
        <Stat icon={Users} tint="green" label="Subjects"
          value={d.subject_stats.length || "0"}
          sub={`${d.subject_stats.reduce((n, s) => n + s.student_count, 0)} students`} to="/subjects" />
      </div>

      {/* Today's periods */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>
            <CalendarCheck size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
            Today — {DAY_FULL[d.today] ?? d.today}
          </h2>
          <Link to="/classes" className="btn ghost sm">Timetable</Link>
        </div>
        {d.today_periods.length === 0
          ? <div className="muted small">No classes today.</div>
          : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {d.today_periods.map((p) => <PeriodPill key={p.id} p={p} />)}
            </div>
          )}
      </div>

      {/* Subject stats */}
      {d.subject_stats.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
            <h2 style={{ margin: 0 }}>
              <BookOpen size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
              My subjects — marks
            </h2>
            <Link to="/subjects" className="btn ghost sm">All</Link>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr><th>Subject</th><th>Class</th><th>Students</th><th>Avg %</th><th>Weak</th><th>Strong</th></tr>
              </thead>
              <tbody>
                {d.subject_stats.map((sub) => (
                  <tr key={sub.id}>
                    <td><Link to={`/subjects/${sub.id}`} style={{ fontWeight: 600 }}>{sub.name}</Link></td>
                    <td><span className="chip">Class {sub.grade}</span></td>
                    <td>{sub.student_count}</td>
                    <td>{sub.avg_pct == null ? <span className="muted">–</span> : <Badge kind={tone(sub.avg_pct)}>{sub.avg_pct}%</Badge>}</td>
                    <td>{sub.weak_count > 0 ? <Badge kind="bad">{sub.weak_count}</Badge> : <span className="muted">0</span>}</td>
                    <td>{sub.strong_count > 0 ? <Badge kind="good">{sub.strong_count}</Badge> : <span className="muted">0</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Weekly schedule compact */}
      {activeDays.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ margin: "0 0 10px" }}>
            <CalendarClock size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
            Weekly schedule
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {activeDays.map((day) => (
              <div key={day}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, color: day === d.today ? "var(--primary)" : "var(--muted)", marginBottom: 4, display: "flex", alignItems: "center", gap: 5 }}>
                  {day === d.today && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--primary)", display: "inline-block" }} />}
                  {DAY_FULL[day]}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {(d.week_schedule[day] ?? []).map((p) => (
                    <div key={p.id} style={{ padding: "3px 9px", borderRadius: 5, fontSize: 12, background: day === d.today ? "var(--primary-soft,#ede9fe)" : "var(--surface,#f7f8fa)", border: "1px solid var(--border)" }}>
                      <b>P{p.period_number}</b>{p.subject_name && ` · ${p.subject_name}`}
                      <span className="muted" style={{ marginLeft: 3 }}>{p.grade}-{p.section}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending student leaves notice */}
      {d.reviewer_pending > 0 && (
        <div className="notice" style={{ marginBottom: 16 }}>
          <ClipboardList size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
          <b>{d.reviewer_pending}</b> student leave{d.reviewer_pending !== 1 ? "s" : ""} awaiting your review.{" "}
          <Link to="/leaves">Review now →</Link>
        </div>
      )}
    </>
  );
}

function StudentWidgets() {
  return (
    <div className="grid g4" style={{ marginBottom: 16 }}>
      <Stat icon={Users} tint="indigo" label="My profile" value="" sub="Marks & attendance" to="/me" />
      <Stat icon={CalendarCheck} tint="green" label="Attendance" value="" sub="View records" to="/me?tab=attendance" />
      <Stat icon={BookOpen} tint="sky" label="Marks" value="" sub="All exams" to="/me?tab=marks" />
      <Stat icon={ClipboardList} tint="amber" label="My leaves" value="" sub="Apply & track" to="/leaves" />
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────
export default function MyBoard() {
  const { session, role, isStudent } = useAuth();
  const isStaff = role === "staff";

  // Notes state
  const [notesTick, setNotesTick] = useState(0);
  const notesState = useLoad(() => api("/myboard/notes"), [notesTick]);
  const reloadNotes = () => setNotesTick((t) => t + 1);

  // Staff dashboard data
  const dashState = useLoad(() => isStaff ? api("/staff/me/dashboard") : Promise.resolve(null), []);

  // Announcements + holidays (for everyone)
  const announcementsState = useLoad(() => api("/announcements?page_size=5"), []);
  const holidaysState = useLoad(() => api("/holidays/upcoming?days=30"), []);

  async function createNote(data) {
    await api("/myboard/notes", { method: "POST", body: data });
    reloadNotes();
  }
  async function saveNote(id, data) {
    await api(`/myboard/notes/${id}`, { method: "PUT", body: data });
    reloadNotes();
  }
  async function deleteNote(id) {
    await api(`/myboard/notes/${id}`, { method: "DELETE" });
    reloadNotes();
  }

  return (
    <>
      <PageHead title="My Board" sub="Your personal workspace — notes, schedule and updates" />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20, alignItems: "start" }}>

        {/* ── Left: dashboard widgets ──────────────────────────────────── */}
        <div>
          {isStaff && dashState.data && <StaffWidgets d={dashState.data} />}
          {isStaff && dashState.loading && <div className="empty">Loading your schedule…</div>}
          {isStudent && <StudentWidgets />}

          {/* Announcements */}
          {announcementsState.data && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                <h2 style={{ margin: 0 }}>
                  <Megaphone size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
                  Announcements
                </h2>
                <Link to="/announcements" className="btn ghost sm">All</Link>
              </div>
              {announcementsState.data.items?.length === 0 && <div className="muted">No recent announcements.</div>}
              {(announcementsState.data.items ?? announcementsState.data).slice(0, 5).map((a) => (
                <div key={a.id} style={{ marginBottom: 10, paddingBottom: 10, borderBottom: "1px solid var(--border)" }}>
                  <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                    <b style={{ fontSize: 13 }}>{a.pinned && "📌 "}{a.title}</b>
                    <span className="small muted">{(a.created_at ?? a.date ?? "").slice(0, 10)}</span>
                  </div>
                  <div className="small muted" style={{ marginTop: 3 }}>
                    {(a.body ?? "").slice(0, 130)}{(a.body ?? "").length > 130 ? "…" : ""}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Upcoming holidays */}
          {holidaysState.data && (
            <div className="card">
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                <h2 style={{ margin: 0 }}>
                  <CalendarRange size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
                  Upcoming holidays
                </h2>
                <Link to="/holidays" className="btn ghost sm">Calendar</Link>
              </div>
              {holidaysState.data.length === 0 && <div className="muted small">No holidays in the next 30 days.</div>}
              {holidaysState.data.slice(0, 5).map((h) => (
                <div key={h.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                  <div>
                    <b style={{ fontSize: 13 }}>{h.name}</b>
                    <div className="small muted">{h.date}</div>
                  </div>
                  <Badge kind={h.category === "national" ? "bad" : h.category === "regional" ? "warn" : "good"}>
                    {h.category}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right: sticky notes ──────────────────────────────────────── */}
        <div>
          <div style={{ marginBottom: 14 }}>
            <h2 style={{ margin: "0 0 4px", display: "flex", alignItems: "center", gap: 8 }}>
              📌 My Notes
            </h2>
            <div className="muted small">Only you can see these.</div>
          </div>

          <NoteComposer onCreate={createNote} />

          {notesState.loading && <div className="muted small">Loading…</div>}
          {!notesState.loading && notesState.data?.length === 0 && (
            <div className="muted small" style={{ textAlign: "center", padding: "24px 0" }}>
              No notes yet — write your first one above!
            </div>
          )}
          <div className="sticky-grid">
            {(notesState.data ?? []).map((n) => (
              <StickyNote key={n.id} note={n} onSave={saveNote} onDelete={deleteNote} />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
