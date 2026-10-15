import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { AlertTriangle, Building2, Eye, GraduationCap, KeyRound, MapPin, Pencil, Plus, Power, Search, Trash2, Users, Wallet } from "lucide-react";
import { api, inr } from "../api.js";
import { schoolFields } from "../forms.js";
import { SUB_KIND, schoolInitial, usageKind } from "../platform.js";
import { Async, Badge, Confirm, FormModal, Meter, PageHead, Secret, Stat, useLoad } from "../components/ui.jsx";

const COLORS = ["#5b4bdb", "#0ea5e9", "#16a34a", "#f59e0b", "#e11d48", "#7c6cf0"];

const createFields = [...schoolFields.slice(0, 1), { key: "owner_name", label: "Owner full name", required: true, full: true }, ...schoolFields.slice(1)];

export default function Schools() {
  const nav = useNavigate();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const [secret, setSecret] = useState(null);
  const [q, setQ] = useState("");
  const state = useLoad(async () => {
    const [overview, schools] = await Promise.all([api("/platform/overview"), api("/schools")]);
    return { overview, schools };
  }, [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <>
      <PageHead title="Platform Console" sub="Every school on the platform: usage, fees, subscriptions and controls">
        <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> New school</button>
      </PageHead>
      <Async state={state}>
        {({ overview: o, schools }) => {
          const t = o.totals;
          const bySchool = o.schools.map((s) => ({ name: s.name.length > 16 ? `${s.name.slice(0, 15)}…` : s.name, Students: s.students, Staff: s.staff }));
          const fees = o.schools.filter((s) => s.fee_total > 0).map((s) => ({ name: s.name.length > 16 ? `${s.name.slice(0, 15)}…` : s.name, Collected: s.fee_paid, Pending: s.fee_total - s.fee_paid }));
          const plans = Object.entries(o.plans).map(([name, value]) => ({ name, value }));
          const shown = schools.filter((s) => `${s.name} ${s.city ?? ""} ${s.owner?.username ?? ""}`.toLowerCase().includes(q.toLowerCase()));
          return (
            <>
              <div className="grid g4">
                <Stat icon={Building2} tint="indigo" label="Schools" value={t.schools} sub={`${t.active_schools} active · ${t.branches} branches`} />
                <Stat icon={GraduationCap} tint="sky" label="Students" value={t.students} sub="across all schools" />
                <Stat icon={Users} tint="green" label="Staff" value={t.staff} sub={`${t.users} logins in total`} />
                <Stat icon={Wallet} tint="amber" label="Fees collected" value={`${t.collection_pct}%`} sub={`${inr(t.fee_paid)} of ${inr(t.fee_total)}`} />
              </div>

              <div className="grid g2" style={{ marginTop: 16 }}>
                <div className="card">
                  <h2>Students and staff by school</h2>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={bySchool}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" fontSize={12} /><YAxis fontSize={12} allowDecimals={false} />
                      <Tooltip /><Legend />
                      <Bar dataKey="Students" fill="#5b4bdb" radius={[6, 6, 0, 0]} /><Bar dataKey="Staff" fill="#0ea5e9" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="card">
                  <h2>Schools onboarded (last 12 months)</h2>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={o.growth}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="month" fontSize={11} tickFormatter={(m) => m.slice(2)} />
                      <YAxis fontSize={12} allowDecimals={false} /><Tooltip />
                      <Line type="monotone" dataKey="schools" name="Schools" stroke="#16a34a" strokeWidth={3} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="card">
                  <h2>Fee collection by school ({o.year})</h2>
                  {fees.length === 0 ? <div className="muted">No fees recorded yet.</div> : (
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={fees}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" fontSize={12} />
                        <YAxis fontSize={12} tickFormatter={(v) => `${Math.round(v / 1000)}k`} /><Tooltip formatter={(v) => inr(v)} /><Legend />
                        <Bar dataKey="Collected" stackId="f" fill="#16a34a" /><Bar dataKey="Pending" stackId="f" fill="#f59e0b" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
                <div className="card">
                  <h2>Students by class (all schools)</h2>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={o.grades}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="grade" fontSize={12} /><YAxis fontSize={12} allowDecimals={false} />
                      <Tooltip /><Bar dataKey="students" name="Students" fill="#7c6cf0" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="grid g3" style={{ marginTop: 16 }}>
                <div className="card">
                  <h2>Plans</h2>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={plans} dataKey="value" nameKey="name" innerRadius={45} outerRadius={78} paddingAngle={2}>
                        {plans.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Pie><Tooltip /><Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="card">
                  <h2><AlertTriangle size={16} style={{ verticalAlign: -2 }} /> Needs attention</h2>
                  {o.attention.length === 0 && <div className="muted">Everything looks healthy.</div>}
                  {o.attention.map((a, i) => (
                    <div key={i} className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                      <Link to={`/schools/${a.id}`}><b>{a.name}</b></Link><Badge kind="warn">{a.reason}</Badge>
                    </div>
                  ))}
                </div>
                <div className="card">
                  <h2>Recent activity</h2>
                  {o.recent_activity.length === 0 && <div className="muted">No activity yet.</div>}
                  {o.recent_activity.map((a) => (
                    <div key={a.id} style={{ marginBottom: 8 }}>
                      <b>{a.action.replaceAll("_", " ")}</b> <span className="muted">· {a.school_name ?? "platform"}</span>
                      <div className="small muted">{a.actor} · {a.at.slice(0, 16).replace("T", " ")}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="row" style={{ justifyContent: "space-between", margin: "26px 0 12px" }}>
                <h2 style={{ margin: 0 }}>All schools</h2>
                <div className="search">
                  <Search size={15} />
                  <input placeholder="Search name, city or owner ID…" aria-label="Search schools" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
              </div>
              {shown.length === 0 && <div className="empty">No schools match.</div>}
              <div className="grid g2">
                {shown.map((s) => (
                  <div key={s.id} className="card">
                    <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div>
                        <Link to={`/schools/${s.id}`} style={{ fontSize: 17, fontWeight: 700 }}>{s.name}</Link>
                        <div className="small muted"><MapPin size={12} /> {[s.city, s.state].filter(Boolean).join(", ") || "Location not set"} · {s.board || "Board not set"}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        {s.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}{" "}
                        <Badge>{s.plan}</Badge>
                      </div>
                    </div>
                    <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", margin: "14px 0 10px", textAlign: "center" }}>
                      {[["Students", s.students], ["Staff", s.staff], ["Branches", s.branches], ["Logins", s.users]].map(([l, v]) => (
                        <div key={l}><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div><div className="small muted">{l}</div></div>
                      ))}
                    </div>
                    <div className="small muted" style={{ marginBottom: 4 }}>Student limit · {s.student_usage.used} / {s.student_usage.max}</div>
                    <Meter pct={s.student_usage.pct} kind={usageKind(s.student_usage.pct)} />
                    <div className="row small" style={{ justifyContent: "space-between", margin: "10px 0 14px" }}>
                      <span className="muted">Owner: {s.owner ? `${s.owner.name} (${s.owner.username})` : "–"}</span>
                      <span>Subscription <Badge kind={SUB_KIND[s.subscription_status]}>{s.subscription_status}{s.subscription_end ? ` · ${s.subscription_end}` : ""}</Badge></span>
                    </div>
                    <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                      <button className="btn sm" onClick={() => nav(`/schools/${s.id}`)}><Eye size={14} /> Details</button>
                      <button className="btn ghost sm" onClick={() => setDlg({ type: "edit", s })}><Pencil size={14} /> Edit</button>
                      <button className="btn ghost sm" onClick={() => nav(`/schools/${s.id}?tab=branches`)}><Building2 size={14} /> Branches</button>
                      <button className="btn ghost sm" onClick={() => setDlg({ type: "reset", s })}><KeyRound size={14} /> Owner password</button>
                      <button className="btn ghost sm" onClick={() => setDlg({ type: "toggle", s })}><Power size={14} /> {s.active ? "Disable" : "Enable"}</button>
                      <button className="icon-btn danger" title="Delete" aria-label={`Delete ${s.name}`} onClick={() => setDlg({ type: "del", s })}><Trash2 size={15} /></button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          );
        }}
      </Async>
      {dlg?.type === "add" && (
        <FormModal title="Create school" fields={createFields} submitLabel="Create" onClose={() => setDlg(null)}
          onSubmit={async (b) => {
            const r = await api("/schools", { method: "POST", body: b });
            setSecret({ title: `${r.school.name} created`, username: r.owner.username, password: r.owner.temp_password, idLabel: "Owner login ID" });
            reload();
          }} />
      )}
      {dlg?.type === "edit" && (
        <FormModal title={`Edit ${dlg.s.name}`} fields={schoolFields} initial={schoolInitial(dlg.s)} onClose={() => setDlg(null)}
          onSubmit={async (b) => { await api(`/schools/${dlg.s.id}`, { method: "PUT", body: b }); reload(); }} />
      )}
      {dlg?.type === "reset" && (
        <Confirm danger={false} title="Reset owner password" message={`Generate a new temporary password for the owner of ${dlg.s.name}?`}
          onClose={() => setDlg(null)} onConfirm={async () => {
            const r = await api(`/schools/${dlg.s.id}/owner/reset-password`, { method: "POST" });
            setSecret({ title: "Password reset", username: r.username, password: r.temp_password, idLabel: "Owner login ID" });
          }} />
      )}
      {dlg?.type === "toggle" && (
        <Confirm danger={dlg.s.active} title={dlg.s.active ? "Disable school" : "Enable school"}
          message={dlg.s.active ? `Everyone at ${dlg.s.name} will be unable to sign in.` : `Re-enable sign-in for ${dlg.s.name}?`}
          onClose={() => setDlg(null)} onConfirm={async () => { await api(`/schools/${dlg.s.id}/active`, { method: "PUT", body: { active: !dlg.s.active } }); reload(); }} />
      )}
      {dlg?.type === "del" && (
        <Confirm title="Delete school" message={`Permanently delete ${dlg.s.name} and ALL its students, staff, marks, fees, users and photos? This cannot be undone.`}
          onClose={() => setDlg(null)} onConfirm={async () => { await api(`/schools/${dlg.s.id}`, { method: "DELETE" }); reload(); }} />
      )}
      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
    </>
  );
}
