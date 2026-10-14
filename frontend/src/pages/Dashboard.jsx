import { Link } from "react-router-dom";
import { Bar, CartesianGrid, BarChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, gradeLabel, inr } from "../api.js";
import { Async, Badge, PageHead, Stat, tone, useLoad } from "../components/ui.jsx";

const COLORS = ["#16a34a", "#4f46e5", "#f59e0b", "#fb923c", "#dc2626"];

export default function Dashboard() {
  const state = useLoad(() => api("/dashboard"));
  return (
    <Async state={state}>
      {(d) => {
        const dist = Object.entries(d.distribution).map(([name, value]) => ({ name, value }));
        const grades = d.by_grade.map((g) => ({ ...g, label: g.grade, avg: g.avg_pct ?? 0 }));
        return (
          <>
            <PageHead title="Dashboard" sub={`Academic year ${d.year}`} />
            <div className="grid g4">
              <Stat label="Students" value={d.total_students} sub="LKG to Class 10" />
              <Stat label="Staff" value={d.staff_count} />
              <Stat label="Average score" value={`${d.avg_pct ?? "–"}%`} sub="all tests this year" />
              <Stat label="Fee collected" value={`${d.fees.collection_pct}%`} sub={`${inr(d.fees.paid)} of ${inr(d.fees.total)}`} />
            </div>
            <div className="grid g2" style={{ marginTop: 16 }}>
              <div className="card">
                <h2>Average score by class</h2>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={grades}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" fontSize={12} /><YAxis domain={[0, 100]} fontSize={12} />
                    <Tooltip /><Bar dataKey="avg" name="Avg %" fill="#4f46e5" radius={[6, 6, 0, 0]} />
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
              <div className="card">
                <h2>Upcoming events</h2>
                {d.upcoming_events.length === 0 && <div className="muted">Nothing scheduled.</div>}
                {d.upcoming_events.map((e) => (
                  <div key={e.id} className="row" style={{ marginBottom: 10 }}>
                    <div className="timeline-date">{e.date.slice(5)}</div>
                    <div><b>{e.title}</b><div className="small muted">{e.category}</div></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid g3" style={{ marginTop: 16 }}>
              <List title="Top performers" items={d.top_students} render={(s) => <Badge kind="good">{s.pct}%</Badge>} />
              <List title="Needs support (below 50%)" items={d.at_risk} render={(s) => <Badge kind="bad">{s.pct}%</Badge>} empty="No students below 50%." />
              <List title="Highest fee dues" items={d.top_defaulters} render={(s) => <Badge kind="warn">{inr(s.pending)}</Badge>} empty="No pending dues." />
            </div>
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
