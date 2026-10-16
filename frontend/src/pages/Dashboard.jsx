import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BookOpen, CalendarDays, CalendarRange, ClipboardList, FileText, GraduationCap, Images, PartyPopper, Sparkles, Target, TrendingUp, Users, Wallet } from "lucide-react";
import { api, gradeLabel, inr } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, PageHead, Stat, useLoad } from "../components/ui.jsx";

const COLORS = ["#16a34a", "#5b4bdb", "#f59e0b", "#fb923c", "#e11d48"];

const CATEGORY_COLOR = { national: "#e11d48", regional: "#f59e0b", school: "#5b4bdb" };

function HolidayBanner({ holidays }) {
  if (!holidays || holidays.length === 0) return null;
  const today = new Date().toISOString().slice(0, 10);
  const todayH = holidays.filter((h) => h.date === today);
  const upcoming = holidays.filter((h) => h.date > today);

  return (
    <div style={{
      borderRadius: 12,
      padding: "12px 18px",
      marginBottom: 16,
      background: "linear-gradient(135deg, #f0f4ff 0%, #fefce8 100%)",
      border: "1px solid #e0e7ff",
      display: "flex",
      flexWrap: "wrap",
      gap: 10,
      alignItems: "center",
    }}>
      <PartyPopper size={20} style={{ color: "#5b4bdb", flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 200 }}>
        {todayH.length > 0 && (
          <div style={{ fontWeight: 700, color: "#5b4bdb", marginBottom: 4 }}>
            🎉 Today: {todayH.map((h) => h.name).join(", ")}
          </div>
        )}
        {upcoming.length > 0 && (
          <div style={{ fontSize: 13, color: "#374151" }}>
            <span style={{ fontWeight: 600 }}>Upcoming: </span>
            {upcoming.slice(0, 5).map((h, i) => (
              <span key={h.id}>
                {i > 0 && " · "}
                <span style={{ color: CATEGORY_COLOR[h.category] ?? "#5b4bdb" }}>
                  {h.name}
                </span>
                <span style={{ color: "#6b7280", fontSize: 11 }}> ({h.date.slice(5)})</span>
              </span>
            ))}
            {upcoming.length > 5 && <span className="muted"> +{upcoming.length - 5} more</span>}
          </div>
        )}
      </div>
      <Link to="/holidays" className="btn ghost sm" style={{ flexShrink: 0 }}>
        <CalendarRange size={13} /> View calendar
      </Link>
    </div>
  );
}

export default function Dashboard() {
  const { can, session } = useAuth();
  const state = useLoad(() => api("/dashboard"));
  const holidayState = useLoad(() => api("/holidays/upcoming?days=30"));
  return (
    <Async state={state}>
      {(d) => {
        const seeStudents = can("students.view");
        const seeFees = d.fees != null;
        const dist = Object.entries(d.distribution).map(([name, value]) => ({ name, value }));
        const grades = d.by_grade.map((g) => ({ ...g, label: g.grade, avg: g.avg_pct ?? 0 }));
        const c = d.counts;
        return (
          <>
            <PageHead title="Dashboard" sub={`Academic year ${d.year} · click any tile to open its page`} />

            {/* ── Holiday banner ─────────────────────────────────────────── */}
            {holidayState.data && <HolidayBanner holidays={holidayState.data} />}

            <div className="grid g4">
              <Stat icon={GraduationCap} tint="indigo" label="Students" value={c.students} sub="LKG to Class 10" to="/students" />
              <Stat icon={Users} tint="sky" label="Staff" value={c.staff} sub="Teachers & admin" to="/staff" />
              <Stat icon={BookOpen} tint="green" label="Subjects" value={c.subjects} sub={`${c.chapters} chapters`} to="/subjects" />
              <Stat icon={CalendarDays} tint="amber" label="Events" value={c.events} sub="Upcoming & past" to="/events" />
              <Stat icon={Images} tint="rose" label="Gallery" value={c.gallery} sub="Photos" to="/gallery" />
              <Stat icon={Target} tint="violet" label="Future goals" value={c.goals} sub="Tracked" to="/goals" />
              {seeStudents && <Stat icon={TrendingUp} tint="teal" label="Average score" value={`${d.avg_pct ?? "–"}%`} sub="all tests this year" to="/students" />}
              {seeFees && <Stat icon={Wallet} tint="amber" label="Fee collected" value={`${d.fees.collection_pct}%`} sub={`${inr(d.fees.paid)} of ${inr(d.fees.total)}`} to="/fees" />}
              {seeFees && <Stat icon={FileText} tint="rose" label="Fees pending" value={inr(d.fees.pending)} sub="open the fee register" to="/fees" />}
              {!session?.isStudent && <Stat icon={ClipboardList} tint="sky" label="Leaves" value="" sub="Staff leave requests" to="/leaves" />}
              <Stat icon={CalendarRange} tint="green" label="Holidays" value="" sub="School calendar" to="/holidays" />
            </div>

            {seeStudents && (
              <div className="grid g2" style={{ marginTop: 16 }}>
                <div className="card">
                  <h2>Average score by class</h2>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={grades}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="label" fontSize={12} /><YAxis domain={[0, 100]} fontSize={12} />
                      <Tooltip /><Bar dataKey="avg" name="Avg %" fill="#5b4bdb" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="card">
                  <h2>Score distribution</h2>
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie data={dist} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                        {dist.map((_, i) => <Cell key={i} fill={COLORS[i]} />)}
                      </Pie>
                      <Tooltip /><Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {seeFees && (
                  <div className="card">
                    <h2>Pending fees by class</h2>
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={grades}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="label" fontSize={12} /><YAxis fontSize={12} tickFormatter={(v) => `${v / 1000}k`} />
                        <Tooltip formatter={(v) => inr(v)} /><Bar dataKey="pending_fee" name="Pending" fill="#f59e0b" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <div className="card">
                  <div className="row" style={{ justifyContent: "space-between" }}><h2>Upcoming events</h2><Link to="/events">View all</Link></div>
                  {d.upcoming_events.length === 0 && <div className="muted">Nothing scheduled.</div>}
                  {d.upcoming_events.map((e) => (
                    <div key={e.id} className="row" style={{ marginBottom: 10 }}>
                      <div className="timeline-date">{e.date.slice(5)}</div>
                      <div><b>{e.title}</b><div className="small muted">{e.category}</div></div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {seeStudents && (
              <div className="grid g3" style={{ marginTop: 16 }}>
                <List title="Top performers" items={d.top_students} render={(s) => <Badge kind="good">{s.pct}%</Badge>} />
                <List title="Needs support (below 50%)" items={d.at_risk} render={(s) => <Badge kind="bad">{s.pct}%</Badge>} empty="No students below 50%." />
                {seeFees && <List title="Highest fee dues" items={d.top_defaulters} render={(s) => <Badge kind="warn">{inr(s.pending)}</Badge>} empty="No pending dues." />}
              </div>
            )}
            {d.attendance_alerts?.length > 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <div className="row" style={{ justifyContent: "space-between" }}><h2>Low attendance</h2><Link to="/attendance">Attendance</Link></div>
                {d.attendance_alerts.map((s) => (
                  <div key={s.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                    <Link to={`/students/${s.id}?tab=attendance`}>{s.name}<div className="small muted">{gradeLabel(s.grade)}-{s.section}</div></Link>
                    <Badge kind="bad">{s.pct}% · {s.absent} absent</Badge>
                  </div>
                ))}
              </div>
            )}
            {c.students === 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <h2>Welcome! Your school is empty.</h2>
                <p className="muted">Start by adding your <Link to="/subjects">subjects</Link>, <Link to="/staff">staff</Link> and <Link to="/students">students</Link>, and fill in <Link to="/about">About School</Link>.</p>
              </div>
            )}
          </>
        );
      }}
    </Async>
  );
}

function List({ title, items, render, empty = "No data." }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {items.length === 0 && <div className="muted">{empty}</div>}
      {items.map((s) => (
        <div key={s.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <Link to={`/students/${s.id}`}>{s.name}<div className="small muted">{gradeLabel(s.grade)}-{s.section}</div></Link>
          {render(s)}
        </div>
      ))}
    </div>
  );
}
