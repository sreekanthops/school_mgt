/**
 * StaffHome — personal dashboard for staff members.
 *
 * Sections:
 *  • Header card: photo, name, designation, class head badge
 *  • Today's timetable (periods for the current day)
 *  • Quick-stat row: classes taught, unread messages, pending leaves, reviewer pending
 *  • My Subjects — mark stats table (avg %, top %, weak / strong student counts)
 *  • Weekly schedule — compact 6-day grid
 *  • Recent announcements
 *  • Upcoming holidays
 *  • My recent leaves (apply button)
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Bell, BookOpen, CalendarCheck, CalendarClock, CalendarRange,
  ClipboardList, Megaphone, MessagesSquare, Plus, Star, Users,
} from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, Modal, PageHead, Photo, Stat, tone, useLoad } from "../components/ui.jsx";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_FULL = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday" };
const STATUS_KIND = { pending: "warn", approved: "good", rejected: "bad" };
const LEAVE_TYPES = ["Casual", "Sick", "Earned", "Maternity", "Paternity", "Unpaid", "Other"];

// ── tiny timetable period pill ────────────────────────────────────────────────
function PeriodPill({ p }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "10px 14px", borderRadius: 8,
      background: "var(--surface,#f7f8fa)",
      border: "1px solid var(--border,#e5e7eb)",
      flex: "1 1 200px",
    }}>
      <div style={{ flexShrink: 0, textAlign: "center", minWidth: 36 }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--primary)" }}>P{p.period_number}</div>
        {p.start_time && (
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 1 }}>
            {p.start_time}
          </div>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {p.subject_name || <span style={{ color: "var(--muted)", fontWeight: 400 }}>No subject</span>}
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          Class {p.grade}-{p.section}
          {p.end_time && ` · ${p.start_time}–${p.end_time}`}
        </div>
      </div>
    </div>
  );
}

// ── apply leave modal ─────────────────────────────────────────────────────────
function ApplyLeaveModal({ onClose, onDone }) {
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ from_date: today, to_date: today, leave_type: "Casual", reason: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api("/leaves", { method: "POST", body: f });
      onDone(); onClose();
    } catch (x) { setErr(x.message); }
    finally { setBusy(false); }
  }

  return (
    <Modal title="Apply for Leave" onClose={onClose}>
      <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          <div className="field"><label>From *</label>
            <input type="date" required value={f.from_date} onChange={(e) => set("from_date", e.target.value)} />
          </div>
          <div className="field"><label>To *</label>
            <input type="date" required value={f.to_date} min={f.from_date} onChange={(e) => set("to_date", e.target.value)} />
          </div>
          <div className="field"><label>Type *</label>
            <select value={f.leave_type} onChange={(e) => set("leave_type", e.target.value)}>
              {LEAVE_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <div className="field"><label>Reason</label>
          <textarea rows={3} maxLength={500} value={f.reason}
            onChange={(e) => set("reason", e.target.value)} placeholder="Optional reason" />
        </div>
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Submitting…" : "Submit"}</button>
        </div>
      </form>
    </Modal>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function StaffHome() {
  const { session } = useAuth();
  const [tick, setTick] = useState(0);
  const [applyLeave, setApplyLeave] = useState(false);
  const state = useLoad(() => api("/staff/me/dashboard"), [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(d) => {
        const s = d.staff;
        const hasTodayPeriods = d.today_periods.length > 0;
        const activeDays = DAYS.filter((day) => (d.week_schedule[day] ?? []).length > 0);

        return (
          <>
            <PageHead title="My Dashboard" sub={`Academic year ${d.year} · ${DAY_FULL[d.today] ?? d.today}`}>
              <button className="btn" onClick={() => setApplyLeave(true)}>
                <Plus size={16} /> Apply for leave
              </button>
            </PageHead>

            {/* ── Profile banner ──────────────────────────────────────── */}
            <div className="card" style={{ display: "flex", gap: 20, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
              <Photo kind="staff" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} size={72} />
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <h1 style={{ margin: 0, fontSize: "1.4rem" }}>{s.name}</h1>
                  {s.class_teacher_of && (
                    <span className="chip" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <Star size={11} /> Class Head · {s.class_teacher_of}
                    </span>
                  )}
                </div>
                <div className="muted">{s.designation} · {s.department} · <code>{s.employee_id}</code></div>
                {d.classes_taught.length > 0 && (
                  <div className="chip-list" style={{ marginTop: 6 }}>
                    {d.classes_taught.map((c) => (
                      <span key={`${c.grade}${c.section}`} className="chip">
                        Class {c.grade}-{c.section}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <Link to={`/staff/${s.id}`} className="btn ghost sm">View full profile</Link>
            </div>

            {/* ── Quick stat row ──────────────────────────────────────── */}
            <div className="grid g4" style={{ marginBottom: 16 }}>
              <Stat icon={CalendarClock} tint="indigo" label="Classes this week"
                value={activeDays.reduce((n, day) => n + (d.week_schedule[day]?.length ?? 0), 0)}
                sub={`across ${activeDays.length} day${activeDays.length !== 1 ? "s" : ""}`} to="/classes" />
              <Stat icon={MessagesSquare} tint="sky" label="Unread messages"
                value={d.unread_messages || "0"}
                sub={d.unread_messages > 0 ? "Tap to open" : "All read"} to="/messages" />
              <Stat icon={ClipboardList} tint="amber" label="My pending leaves"
                value={d.pending_leaves || "0"}
                sub={d.reviewer_pending > 0 ? `${d.reviewer_pending} awaiting your review` : "Nothing pending"} to="/leaves" />
              <Stat icon={Users} tint="green" label="My subjects"
                value={d.subject_stats.length || "0"}
                sub={`${d.subject_stats.reduce((n, s) => n + s.student_count, 0)} students`} to="/subjects" />
            </div>

            {/* ── Today's schedule ────────────────────────────────────── */}
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <h2 style={{ margin: 0 }}>
                  <CalendarCheck size={17} style={{ verticalAlign: -3, marginRight: 6 }} />
                  Today — {DAY_FULL[d.today] ?? d.today}
                </h2>
                <Link to="/classes" className="btn ghost sm">Full timetable</Link>
              </div>
              {!hasTodayPeriods && (
                <div className="muted" style={{ padding: "12px 0" }}>
                  No classes scheduled for today.{" "}
                  {activeDays.length > 0 && `Next class day: ${DAY_FULL[activeDays[0]]}.`}
                </div>
              )}
              {hasTodayPeriods && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {d.today_periods.map((p) => <PeriodPill key={p.id} p={p} />)}
                </div>
              )}
            </div>

            <div className="grid g2" style={{ alignItems: "start" }}>

              {/* ── My Subjects & mark stats ─────────────────────────── */}
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                  <h2 style={{ margin: 0 }}>
                    <BookOpen size={17} style={{ verticalAlign: -3, marginRight: 6 }} />
                    My Subjects — marks overview
                  </h2>
                  <Link to="/subjects" className="btn ghost sm">All subjects</Link>
                </div>
                {d.subject_stats.length === 0 && (
                  <div className="muted">No subjects assigned yet. Set your subjects in your staff profile.</div>
                )}
                {d.subject_stats.length > 0 && (
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Subject</th>
                          <th>Class</th>
                          <th>Students</th>
                          <th>Avg %</th>
                          <th>Top %</th>
                          <th>Weak</th>
                          <th>Strong</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.subject_stats.map((sub) => (
                          <tr key={sub.id}>
                            <td>
                              <Link to={`/subjects/${sub.id}`} style={{ fontWeight: 600 }}>
                                {sub.name}
                              </Link>
                            </td>
                            <td><span className="chip">Class {sub.grade}</span></td>
                            <td>{sub.student_count}</td>
                            <td>
                              {sub.avg_pct == null
                                ? <span className="muted">–</span>
                                : <Badge kind={tone(sub.avg_pct)}>{sub.avg_pct}%</Badge>}
                            </td>
                            <td>
                              {sub.top_pct == null
                                ? <span className="muted">–</span>
                                : <span style={{ color: "var(--good,#16a34a)", fontWeight: 600 }}>{sub.top_pct}%</span>}
                            </td>
                            <td>
                              {sub.weak_count > 0
                                ? <Badge kind="bad">{sub.weak_count}</Badge>
                                : <span className="muted">0</span>}
                            </td>
                            <td>
                              {sub.strong_count > 0
                                ? <Badge kind="good">{sub.strong_count}</Badge>
                                : <span className="muted">0</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* ── Weekly schedule ──────────────────────────────────── */}
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                  <h2 style={{ margin: 0 }}>
                    <CalendarClock size={17} style={{ verticalAlign: -3, marginRight: 6 }} />
                    Weekly schedule
                  </h2>
                  <Link to="/classes" className="btn ghost sm">Edit</Link>
                </div>
                {activeDays.length === 0 && (
                  <div className="muted">No timetable slots assigned yet.</div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {activeDays.map((day) => (
                    <div key={day}>
                      <div style={{
                        fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1,
                        color: day === d.today ? "var(--primary)" : "var(--muted)",
                        marginBottom: 4,
                        display: "flex", alignItems: "center", gap: 6,
                      }}>
                        {day === d.today && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--primary)", display: "inline-block" }} />}
                        {DAY_FULL[day]}
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {(d.week_schedule[day] ?? []).map((p) => (
                          <div key={p.id} style={{
                            padding: "4px 10px", borderRadius: 6, fontSize: 12,
                            background: day === d.today ? "var(--primary-soft,#ede9fe)" : "var(--surface,#f7f8fa)",
                            border: "1px solid var(--border,#e5e7eb)",
                            color: "var(--text,#1f2328)",
                          }}>
                            <b>P{p.period_number}</b>
                            {p.subject_name && ` · ${p.subject_name}`}
                            <span className="muted" style={{ marginLeft: 4 }}>{p.grade}-{p.section}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* ── Recent announcements ─────────────────────────────── */}
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                  <h2 style={{ margin: 0 }}>
                    <Megaphone size={17} style={{ verticalAlign: -3, marginRight: 6 }} />
                    Announcements
                  </h2>
                  <Link to="/announcements" className="btn ghost sm">All</Link>
                </div>
                {d.announcements.length === 0 && <div className="muted">No recent announcements.</div>}
                {d.announcements.map((a) => (
                  <div key={a.id} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--border,#e5e7eb)" }}>
                    <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                      <b>{a.pinned && "📌 "}{a.title}</b>
                      <span className="small muted">{a.created_at.slice(0, 10)}</span>
                    </div>
                    <div className="small muted" style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>
                      {a.body.length > 150 ? a.body.slice(0, 150) + "…" : a.body}
                    </div>
                  </div>
                ))}
              </div>

              {/* ── Upcoming holidays ────────────────────────────────── */}
              <div className="card">
                  <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                    <h2 style={{ margin: 0 }}>
                      <CalendarRange size={17} style={{ verticalAlign: -3, marginRight: 6 }} />
                      Upcoming holidays
                    </h2>
                    <Link to="/holidays" className="btn ghost sm">Calendar</Link>
                  </div>
                  {d.upcoming_holidays.length === 0 && <div className="muted">No holidays in the next 30 days.</div>}
                  {d.upcoming_holidays.map((h) => (
                    <div key={h.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                      <div>
                        <b>{h.name}</b>
                        <div className="small muted">{h.date}</div>
                      </div>
                      <Badge kind={h.category === "national" ? "bad" : h.category === "regional" ? "warn" : "good"}>
                        {h.category}
                      </Badge>
                    </div>
                  ))}
              </div>

              {/* ── My leaves ────────────────────────────────────────── */}
              <div className="card">
                  <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                    <h2 style={{ margin: 0 }}>
                      <Bell size={17} style={{ verticalAlign: -3, marginRight: 6 }} />
                      My leaves
                    </h2>
                    <Link to="/leaves" className="btn ghost sm">All leaves</Link>
                  </div>
                  {d.reviewer_pending > 0 && (
                    <div className="notice" style={{ marginBottom: 10, fontSize: 13 }}>
                      <ClipboardList size={13} style={{ verticalAlign: -2 }} />{" "}
                      <b>{d.reviewer_pending}</b> student leave{d.reviewer_pending !== 1 ? "s" : ""} awaiting your review.{" "}
                      <Link to="/leaves">Review now →</Link>
                    </div>
                  )}
                  {d.recent_leaves.length === 0 && <div className="muted">No leave applications yet.</div>}
                  {d.recent_leaves.map((l) => (
                    <div key={l.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                      <div>
                        <b>{l.leave_type}</b>
                        <div className="small muted">{l.from_date} – {l.to_date} · {l.days} day{l.days !== 1 ? "s" : ""}</div>
                      </div>
                      <Badge kind={STATUS_KIND[l.status]}>{l.status}</Badge>
                    </div>
                  ))}
              </div>

            </div>

            {applyLeave && <ApplyLeaveModal onClose={() => setApplyLeave(false)} onDone={reload} />}
          </>
        );
      }}
    </Async>
  );
}
