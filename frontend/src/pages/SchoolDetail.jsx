import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  ArrowLeft, Building2, CalendarDays, Crown, Globe, GraduationCap, KeyRound, Mail, MapPin, Pencil, Phone, Plus, Power, Star, Trash2, Users, Wallet,
} from "lucide-react";
import { api, gradeLabel, inr } from "../api.js";
import { branchFields, schoolFields } from "../forms.js";
import { SUB_KIND, schoolInitial, usageKind } from "../platform.js";
import { Async, Badge, Confirm, Empty, FormModal, Meter, PageHead, Secret, Stat, useLoad } from "../components/ui.jsx";

const COLORS = ["#5b4bdb", "#0ea5e9", "#f59e0b", "#e11d48", "#16a34a"];
const TABS = [["overview", "Overview"], ["academics", "Academics & fees"], ["branches", "Branches"], ["people", "Owner & staff logins"], ["activity", "Activity"]];
const when = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") : "Never");

export default function SchoolDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [search, setSearch] = useSearchParams();
  const tab = TABS.some(([k]) => k === search.get("tab")) ? search.get("tab") : "overview";
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const [secret, setSecret] = useState(null);
  const state = useLoad(() => api(`/schools/${id}`), [id, tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <>
      <Link to="/schools" className="backlink"><ArrowLeft size={14} /> All schools</Link>
      <Async state={state}>
        {(s) => (
          <>
            <PageHead title={s.name} sub={`${[s.city, s.state].filter(Boolean).join(", ") || "Location not set"} · ${s.board || "Board not set"} · School ID ${s.id}`}>
              {s.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}
              <Badge>{s.plan}</Badge>
              <button className="btn ghost" onClick={() => setDlg({ type: "edit" })}><Pencil size={15} /> Edit details</button>
              <button className="btn ghost" onClick={() => setDlg({ type: "toggle" })}><Power size={15} /> {s.active ? "Disable" : "Enable"}</button>
              <button className="btn danger" onClick={() => setDlg({ type: "del" })}><Trash2 size={15} /> Delete</button>
            </PageHead>

            <div className="grid g4">
              <Stat icon={GraduationCap} tint="indigo" label="Students" value={s.counts.students} sub={`${s.usage.students.used} of ${s.usage.students.max} allowed`} />
              <Stat icon={Users} tint="sky" label="Staff" value={s.counts.staff} sub={`${s.usage.staff.used} of ${s.usage.staff.max} allowed`} />
              <Stat icon={Building2} tint="green" label="Branches" value={s.counts.branches} sub={`${s.counts.subjects} subjects · ${s.counts.chapters} chapters`} />
              <Stat icon={Wallet} tint="amber" label="Fees collected" value={s.fees ? `${s.fees.collection_pct}%` : "–"} sub={s.fees ? `${inr(s.fees.pending)} pending` : ""} />
            </div>

            <div className="tabs" style={{ marginTop: 18 }}>
              {TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setSearch(k === "overview" ? {} : { tab: k })}>{l}</button>)}
            </div>

            {tab === "overview" && <Overview s={s} />}
            {tab === "academics" && <Academics s={s} />}
            {tab === "branches" && <Branches s={s} reload={reload} setDlg={setDlg} />}
            {tab === "people" && <People s={s} reload={reload} setSecret={setSecret} />}
            {tab === "activity" && <Activity s={s} />}

            {dlg?.type === "edit" && (
              <FormModal title={`Edit ${s.name}`} fields={schoolFields} initial={schoolInitial(s)} onClose={() => setDlg(null)}
                onSubmit={async (b) => { await api(`/schools/${s.id}`, { method: "PUT", body: b }); reload(); }} />
            )}
            {dlg?.type === "toggle" && (
              <Confirm danger={s.active} title={s.active ? "Disable school" : "Enable school"}
                message={s.active ? `Everyone at ${s.name} will be unable to sign in.` : `Re-enable sign-in for ${s.name}?`}
                onClose={() => setDlg(null)} onConfirm={async () => { await api(`/schools/${s.id}/active`, { method: "PUT", body: { active: !s.active } }); reload(); }} />
            )}
            {dlg?.type === "del" && (
              <Confirm title="Delete school" message={`Permanently delete ${s.name} and ALL its students, staff, marks, fees, users and photos? This cannot be undone.`}
                onClose={() => setDlg(null)} onConfirm={async () => { await api(`/schools/${s.id}`, { method: "DELETE" }); nav("/schools"); }} />
            )}
            {dlg?.type === "branch" && (
              <FormModal title={dlg.b ? `Edit ${dlg.b.name}` : "Add branch"} fields={branchFields} initial={dlg.b} submitLabel={dlg.b ? "Save" : "Add"}
                onClose={() => setDlg(null)}
                onSubmit={async (b) => {
                  await api(dlg.b ? `/schools/${s.id}/branches/${dlg.b.id}` : `/schools/${s.id}/branches`, { method: dlg.b ? "PUT" : "POST", body: b });
                  reload();
                }} />
            )}
            {dlg?.type === "branch-del" && (
              <Confirm title="Delete branch" message={`Delete ${dlg.b.name}?`} onClose={() => setDlg(null)}
                onConfirm={async () => { await api(`/schools/${s.id}/branches/${dlg.b.id}`, { method: "DELETE" }); reload(); }} />
            )}
            {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
          </>
        )}
      </Async>
    </>
  );
}

function Overview({ s }) {
  const gender = Object.entries(s.gender).map(([name, value]) => ({ name, value }));
  return (
    <div className="grid g2">
      <div className="card">
        <h2>School profile</h2>
        <dl className="kv">
          <dt>Type</dt><dd>{s.school_type || "–"}</dd>
          <dt>Board</dt><dd>{s.board || "–"}</dd>
          <dt>Founded</dt><dd>{s.founded || "–"}</dd>
          <dt>Address</dt><dd><MapPin size={13} /> {s.address || "–"}</dd>
          <dt>Email</dt><dd><Mail size={13} /> {s.email || "–"}</dd>
          <dt>Phone</dt><dd><Phone size={13} /> {s.phone || "–"}</dd>
          <dt>Website</dt><dd><Globe size={13} /> {s.website ? <a href={s.website} target="_blank" rel="noreferrer noopener">{s.website}</a> : "–"}</dd>
          <dt>On the platform since</dt><dd>{s.created_at}</dd>
        </dl>
        {s.notes && <><h3>Private notes</h3><p className="muted" style={{ whiteSpace: "pre-wrap" }}>{s.notes}</p></>}
      </div>
      <div className="card">
        <h2>Plan and subscription</h2>
        <dl className="kv">
          <dt>Plan</dt><dd><Badge>{s.plan}</Badge></dd>
          <dt>Subscription</dt><dd><Badge kind={SUB_KIND[s.subscription_status]}>{s.subscription_status}</Badge> {s.subscription_end && <span className="muted"><CalendarDays size={13} /> ends {s.subscription_end}</span>}</dd>
          <dt>Owner</dt><dd>{s.owner ? <><Crown size={13} /> {s.owner.name} <code>{s.owner.username}</code></> : "–"}</dd>
          <dt>Owner last login</dt><dd>{when(s.owner?.last_login)}</dd>
          <dt>Last activity</dt><dd>{when(s.last_activity)}</dd>
          <dt>Active users (7 days)</dt><dd>{s.active_users_7d} of {s.counts.users}</dd>
        </dl>
        {[["Student limit", s.usage.students], ["Staff limit", s.usage.staff]].map(([l, u]) => (
          <div key={l} style={{ marginTop: 14 }}>
            <div className="row small" style={{ justifyContent: "space-between" }}><span>{l}</span><span className="muted">{u.used} / {u.max} ({u.pct}%)</span></div>
            <Meter pct={u.pct} kind={usageKind(u.pct)} />
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Content</h2>
        <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", textAlign: "center" }}>
          {[["Subjects", s.counts.subjects], ["Chapters", s.counts.chapters], ["Events", s.counts.events], ["Gallery", s.counts.gallery], ["Goals", s.counts.goals],
            ["Admins", s.roles.admin ?? 0], ["Staff logins", s.roles.staff ?? 0], ["Student logins", s.roles.student ?? 0]].map(([l, v]) => (
            <div key={l}><div style={{ fontSize: 22, fontWeight: 700 }}>{v}</div><div className="small muted">{l}</div></div>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>Student gender mix</h2>
        {gender.length === 0 ? <div className="muted">No students yet.</div> : (
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={gender} dataKey="value" nameKey="name" innerRadius={45} outerRadius={78} paddingAngle={2}>
                {gender.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie><Tooltip /><Legend />
            </PieChart>
          </ResponsiveContainer>
        )}
        {s.staff_by_department.length > 0 && (
          <>
            <h3>Staff by department</h3>
            <div className="chip-list">{s.staff_by_department.map((d) => <span key={d.department} className="chip">{d.department} · {d.count}</span>)}</div>
          </>
        )}
      </div>
    </div>
  );
}

function Academics({ s }) {
  if (s.counts.students === 0) return <Empty>No students yet, so there is nothing to chart.</Empty>;
  const grades = s.by_grade.map((g) => ({ ...g, avg: g.avg_pct ?? 0 }));
  const dist = Object.entries(s.distribution).map(([name, value]) => ({ name, value }));
  return (
    <>
      <div className="grid g2">
        <div className="card">
          <h2>Students per class</h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={grades}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="grade" fontSize={12} /><YAxis fontSize={12} allowDecimals={false} />
              <Tooltip /><Bar dataKey="students" name="Students" fill="#0ea5e9" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h2>Average score by class ({s.year})</h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={grades}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="grade" fontSize={12} /><YAxis domain={[0, 100]} fontSize={12} />
              <Tooltip /><Bar dataKey="avg" name="Avg %" fill="#5b4bdb" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h2>Score distribution</h2>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={dist} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                {dist.map((_, i) => <Cell key={i} fill={["#16a34a", "#5b4bdb", "#f59e0b", "#fb923c", "#e11d48"][i]} />)}
              </Pie><Tooltip /><Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h2>Pending fees by class</h2>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={grades}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="grade" fontSize={12} />
              <YAxis fontSize={12} tickFormatter={(v) => `${v / 1000}k`} /><Tooltip formatter={(v) => inr(v)} />
              <Bar dataKey="pending_fee" name="Pending" fill="#f59e0b" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Fees ({s.year})</h2>
          <dl className="kv"><dt>Billed</dt><dd>{inr(s.fees.total)}</dd><dt>Collected</dt><dd>{inr(s.fees.paid)}</dd><dt>Pending</dt><dd>{inr(s.fees.pending)}</dd></dl>
          <div style={{ marginTop: 12 }}><Meter pct={s.fees.collection_pct} /></div>
        </div>
        <div className="card">
          <h2>Top and at-risk students</h2>
          <div className="small muted">Top performers</div>
          {s.top_students.map((x) => <div key={x.id} className="row" style={{ justifyContent: "space-between" }}><span>{x.name} <span className="muted small">{gradeLabel(x.grade)}-{x.section}</span></span><Badge kind="good">{x.pct}%</Badge></div>)}
          <div className="small muted" style={{ marginTop: 10 }}>Below 50%</div>
          {s.at_risk.length === 0 && <div className="muted small">None.</div>}
          {s.at_risk.map((x) => <div key={x.id} className="row" style={{ justifyContent: "space-between" }}><span>{x.name} <span className="muted small">{gradeLabel(x.grade)}-{x.section}</span></span><Badge kind="bad">{x.pct}%</Badge></div>)}
        </div>
      </div>
    </>
  );
}

function Branches({ s, reload, setDlg }) {
  const [err, setErr] = useState("");
  const setState = async (b, body) => {
    setErr("");
    try { await api(`/schools/${s.id}/branches/${b.id}/state`, { method: "PUT", body }); reload(); } catch (e) { setErr(e.message); }
  };
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div className="muted">{s.branches.length} branch{s.branches.length === 1 ? "" : "es"}</div>
        <button className="btn" onClick={() => setDlg({ type: "branch" })}><Plus size={16} /> Add branch</button>
      </div>
      {err && <div className="error">{err}</div>}
      {s.branches.length === 0 && <Empty>No branches yet.</Empty>}
      <div className="grid g2">
        {s.branches.map((b) => (
          <div key={b.id} className="card">
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div><b style={{ fontSize: 16 }}>{b.name}</b><div className="small muted"><MapPin size={12} /> {[b.city, b.address].filter(Boolean).join(" · ") || "No address"}</div></div>
              <div>{b.is_main && <Badge kind="good"><Star size={11} /> Main</Badge>} {b.active ? null : <Badge kind="gray">Disabled</Badge>}</div>
            </div>
            <dl className="kv" style={{ margin: "12px 0" }}>
              <dt>Principal</dt><dd>{b.principal || "–"}</dd><dt>Phone</dt><dd>{b.phone || "–"}</dd><dt>Email</dt><dd>{b.email || "–"}</dd>
            </dl>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              <button className="btn ghost sm" onClick={() => setDlg({ type: "branch", b })}><Pencil size={14} /> Edit</button>
              {!b.is_main && <button className="btn ghost sm" onClick={() => setState(b, { is_main: true })}><Star size={14} /> Make main</button>}
              {!b.is_main && <button className="btn ghost sm" onClick={() => setState(b, { active: !b.active })}><Power size={14} /> {b.active ? "Disable" : "Enable"}</button>}
              {!b.is_main && <button className="icon-btn danger" aria-label={`Delete ${b.name}`} onClick={() => setDlg({ type: "branch-del", b })}><Trash2 size={15} /></button>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function People({ s, reload, setSecret }) {
  const [dlg, setDlg] = useState(null);
  return (
    <>
      <p className="muted">Owner and staff logins for this school. Student logins are managed by the school itself.</p>
      <div className="card flush" style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>Login ID</th><th>Name</th><th>Role</th><th>Last login</th><th>Status</th><th /></tr></thead>
          <tbody>
            {s.people.map((u) => (
              <tr key={u.id}>
                <td><code>{u.username}</code></td><td>{u.name}</td><td><Badge kind={u.role === "admin" ? "bad" : "warn"}>{u.role === "admin" ? "owner" : u.role}</Badge></td>
                <td className="muted">{when(u.last_login)}</td>
                <td>{u.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn ghost sm" onClick={() => setDlg({ type: "reset", u })}><KeyRound size={14} /> Reset password</button>{" "}
                  <button className="btn ghost sm" onClick={() => setDlg({ type: "toggle", u })}><Power size={14} /> {u.active ? "Disable" : "Enable"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {dlg?.type === "reset" && (
        <Confirm danger={false} title="Reset password" message={`Generate a new temporary password for ${dlg.u.username}?`} onClose={() => setDlg(null)}
          onConfirm={async () => {
            const r = await api(`/schools/${s.id}/users/${dlg.u.id}/reset-password`, { method: "POST" });
            setSecret({ title: "Password reset", username: r.username, password: r.temp_password, idLabel: "Login ID" });
          }} />
      )}
      {dlg?.type === "toggle" && (
        <Confirm danger={dlg.u.active} title={dlg.u.active ? "Disable login" : "Enable login"} message={`${dlg.u.active ? "Disable" : "Enable"} ${dlg.u.username}?`} onClose={() => setDlg(null)}
          onConfirm={async () => { await api(`/schools/${s.id}/users/${dlg.u.id}/active`, { method: "PUT", body: { active: !dlg.u.active } }); reload(); }} />
      )}
    </>
  );
}

function Activity({ s }) {
  if (s.audit.length === 0) return <Empty>No platform actions recorded for this school yet.</Empty>;
  return (
    <div className="card flush" style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th>When (UTC)</th><th>Action</th><th>Detail</th><th>By</th></tr></thead>
        <tbody>{s.audit.map((a) => <tr key={a.id}><td className="muted">{when(a.at)}</td><td><b>{a.action.replaceAll("_", " ")}</b></td><td>{a.detail || "–"}</td><td>{a.actor}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
