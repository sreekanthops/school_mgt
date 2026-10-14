import { useState } from "react";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, Confirm, Modal, PageHead, Secret, useLoad } from "../components/ui.jsx";

const ROLE_KIND = { admin: "bad", staff: "warn", student: "" };

function UserForm({ user, perms, students, staff, onClose, onSaved }) {
  const { role: myRole, can } = useAuth();
  const edit = !!user;
  const [f, setF] = useState({
    username: "", full_name: user?.full_name ?? "", role: "staff", student_id: "", staff_id: "",
    permissions: user?.permissions?.filter((p) => p !== "all") ?? [],
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggle = (k) => set("permissions", f.permissions.includes(k) ? f.permissions.filter((x) => x !== k) : [...f.permissions, k]);
  const role = edit ? user.role : f.role;
  // you can only grant what you hold; only admins can grant user management
  const grantable = (k) => can(k) && (k !== "users.manage" || myRole === "admin");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      if (edit) {
        const body = { full_name: f.full_name };
        if (role === "staff") body.permissions = f.permissions;
        await api(`/users/${user.id}`, { method: "PUT", body });
        onSaved();
      } else {
        const body = { full_name: f.full_name, role, permissions: role === "staff" ? f.permissions : [] };
        // student, admin and linked-staff logins are generated from their ID; only unlinked staff need a name
        if (role === "staff" && !f.staff_id) body.username = f.username;
        if (role === "student") body.student_id = Number(f.student_id) || null;
        if (role === "staff" && f.staff_id) body.staff_id = Number(f.staff_id);
        onSaved(await api("/users", { method: "POST", body }));
      }
      onClose();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={edit ? `Edit ${user.username}` : "Create user"} onClose={onClose} wide>
      <form onSubmit={submit}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          <div className="field"><label htmlFor="u-full">Full name *</label>
            <input id="u-full" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} required minLength={2} /></div>
          {!edit && (
            <div className="field"><label htmlFor="u-role">Role *</label>
              <select id="u-role" value={f.role} onChange={(e) => set("role", e.target.value)}>
                <option value="staff">Staff</option><option value="student">Student</option>
                {myRole === "admin" && <option value="admin">Admin</option>}
              </select></div>
          )}
          {!edit && role === "student" && (
            <div className="field"><label htmlFor="u-stu">Student (login = student ID) *</label>
              <select id="u-stu" value={f.student_id} onChange={(e) => set("student_id", e.target.value)} required>
                <option value="">Select student…</option>
                {students.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.admission_no})</option>)}
              </select></div>
          )}
          {!edit && role === "staff" && (
            <div className="field"><label htmlFor="u-stf">Staff profile (login = staff ID)</label>
              <select id="u-stf" value={f.staff_id} onChange={(e) => set("staff_id", e.target.value)}>
                <option value="">None (choose a username)</option>
                {staff.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.employee_id})</option>)}
              </select></div>
          )}
          {!edit && role === "staff" && !f.staff_id && (
            <div className="field"><label htmlFor="u-name">Username *</label>
              <input id="u-name" value={f.username} onChange={(e) => set("username", e.target.value)} required pattern="[A-Za-z0-9_.\-]{3,50}" title="3-50 letters, digits, . _ -" /></div>
          )}
          {!edit && role === "admin" && <p className="small muted" style={{ gridColumn: "1 / -1" }}>The owner/admin login ID is generated automatically.</p>}
        </div>
        {role === "staff" && (
          <>
            <h3>Permissions</h3>
            <div className="perm-grid">
              {perms.map((p) => (
                <label key={p.key} className="perm">
                  <input type="checkbox" checked={f.permissions.includes(p.key)} disabled={!grantable(p.key) && !f.permissions.includes(p.key)}
                    onChange={() => toggle(p.key)} />
                  <span>{p.label}</span>
                </label>
              ))}
            </div>
          </>
        )}
        <div className="modal-foot">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : edit ? "Save" : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function UsersPage() {
  const { session } = useAuth();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const [secret, setSecret] = useState(null);
  const state = useLoad(async () => {
    const [users, perms, students, staff] = await Promise.all([
      api("/users"), api("/permissions"), api("/students?page_size=100").catch(() => ({ items: [] })), api("/staff").catch(() => []),
    ]);
    return { users, perms, students: students.items, staff };
  }, [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <>
      <PageHead title="Users & Access" sub="Create logins and choose exactly what each person can do">
        <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> Create user</button>
      </PageHead>
      <Async state={state}>
        {(d) => (
          <>
            <div className="card flush" style={{ overflowX: "auto" }}>
              <table>
                <thead><tr><th>User</th><th>Role</th><th>Access</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {d.users.map((u) => (
                    <tr key={u.id}>
                      <td><b>{u.full_name}</b><div className="small muted">{u.username}</div></td>
                      <td><Badge kind={ROLE_KIND[u.role]}>{u.role}</Badge></td>
                      <td style={{ maxWidth: 360 }}>
                        {u.role === "admin" ? "Full access" : u.role === "student" ? "Own profile only" : (
                          <div className="chip-list">{u.permissions.length ? u.permissions.map((p) => <span key={p} className="chip">{p}</span>) : <span className="muted">View only</span>}</div>
                        )}
                      </td>
                      <td>{u.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button className="icon-btn" title="Edit" onClick={() => setDlg({ type: "edit", u })}><Pencil size={15} /></button>
                        <button className="icon-btn" title="Reset password" onClick={() => setDlg({ type: "reset", u })}><KeyRound size={15} /></button>
                        {u.id !== session.id && (
                          <>
                            <button className="btn ghost sm" onClick={async () => { await api(`/users/${u.id}`, { method: "PUT", body: { active: !u.active } }); reload(); }}>
                              {u.active ? "Disable" : "Enable"}
                            </button>
                            <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", u })}><Trash2 size={15} /></button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(dlg?.type === "add" || dlg?.type === "edit") && (
              <UserForm user={dlg.u} perms={d.perms} students={d.students} staff={d.staff} onClose={() => setDlg(null)}
                onSaved={(created) => { reload(); if (created) setSecret({ title: "User created", username: created.username, password: created.temp_password }); }} />
            )}
            {dlg?.type === "reset" && (
              <Confirm danger={false} title="Reset password" message={`Generate a new temporary password for ${dlg.u.username}?`} onClose={() => setDlg(null)}
                onConfirm={async () => {
                  const r = await api(`/users/${dlg.u.id}/reset-password`, { method: "POST" });
                  setSecret({ title: "Password reset", username: r.username, password: r.temp_password });
                }} />
            )}
            {dlg?.type === "del" && (
              <Confirm title="Delete user" message={`Delete login ${dlg.u.username}? Their student or staff record is kept.`} onClose={() => setDlg(null)}
                onConfirm={async () => { await api(`/users/${dlg.u.id}`, { method: "DELETE" }); reload(); }} />
            )}
          </>
        )}
      </Async>
      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
    </>
  );
}
