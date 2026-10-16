import { useState } from "react";
import { ExternalLink, Filter, GraduationCap, KeyRound, Pencil, Plus, Search, ShieldCheck, Trash2, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, Confirm, Modal, PageHead, Secret, useLoad } from "../components/ui.jsx";
import { GRADES } from "../api.js";

// ── create / edit form ────────────────────────────────────────────────────────

function UserForm({ user, perms, students, staff, onClose, onSaved, defaultRole = "staff" }) {
  const { role: myRole, can } = useAuth();
  const edit = !!user;
  const [f, setF] = useState({
    username: "", full_name: user?.full_name ?? "", role: defaultRole, student_id: "", staff_id: "",
    permissions: user?.permissions?.filter((p) => p !== "all") ?? [],
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggle = (k) =>
    set("permissions", f.permissions.includes(k)
      ? f.permissions.filter((x) => x !== k)
      : [...f.permissions, k]);
  const role = edit ? user.role : f.role;
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
          <div className="field">
            <label htmlFor="u-full">Full name *</label>
            <input id="u-full" value={f.full_name}
              onChange={(e) => set("full_name", e.target.value)} required minLength={2} />
          </div>
          {!edit && (
            <div className="field">
              <label htmlFor="u-role">Role *</label>
              <select id="u-role" value={f.role} onChange={(e) => set("role", e.target.value)}>
                <option value="staff">Staff</option>
                <option value="student">Student</option>
                {myRole === "admin" && <option value="admin">Admin</option>}
              </select>
            </div>
          )}
          {!edit && role === "student" && (
            <div className="field">
              <label htmlFor="u-stu">Student (login = student ID) *</label>
              <select id="u-stu" value={f.student_id}
                onChange={(e) => set("student_id", e.target.value)} required>
                <option value="">Select student…</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.name} ({s.admission_no})</option>
                ))}
              </select>
            </div>
          )}
          {!edit && role === "staff" && (
            <div className="field">
              <label htmlFor="u-stf">Staff profile (login = staff ID)</label>
              <select id="u-stf" value={f.staff_id}
                onChange={(e) => set("staff_id", e.target.value)}>
                <option value="">None (choose a username)</option>
                {staff.map((s) => (
                  <option key={s.id} value={s.id}>{s.name} ({s.employee_id})</option>
                ))}
              </select>
            </div>
          )}
          {!edit && role === "staff" && !f.staff_id && (
            <div className="field">
              <label htmlFor="u-name">Username *</label>
              <input id="u-name" value={f.username}
                onChange={(e) => set("username", e.target.value)}
                required pattern="[A-Za-z0-9_.\-]{3,50}" title="3-50 letters, digits, . _ -" />
            </div>
          )}
          {!edit && role === "admin" && (
            <p className="small muted" style={{ gridColumn: "1 / -1" }}>
              The admin login ID is generated automatically.
            </p>
          )}
        </div>
        {role === "staff" && (
          <>
            <h3 style={{ marginTop: 20 }}>Permissions</h3>
            <div className="perm-grid">
              {perms.map((p) => (
                <label key={p.key} className="perm">
                  <input type="checkbox"
                    checked={f.permissions.includes(p.key)}
                    disabled={!grantable(p.key) && !f.permissions.includes(p.key)}
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

// ── shared user row ───────────────────────────────────────────────────────────

function profileLink(u) {
  if (u.staff_id)   return `/staff/${u.staff_id}`;
  if (u.student_id) return `/students/${u.student_id}`;
  return null;
}

function UserRow({ u, session, onEdit, onReset, onToggle, onDel }) {
  const link = profileLink(u);
  return (
    <tr>
      <td>
        <div className="row" style={{ gap: 6, alignItems: "center" }}>
          <div>
            <b>{u.full_name}</b>
            <div className="small muted">{u.username}</div>
          </div>
          {link && (
            <Link to={link} title="View profile"
              style={{ color: "var(--primary)", opacity: 0.7, flexShrink: 0 }}>
              <ExternalLink size={13} />
            </Link>
          )}
        </div>
      </td>
      <td style={{ maxWidth: 340 }}>
        {u.role === "admin"
          ? <span className="muted small">Full access to everything</span>
          : u.role === "student"
            ? <span className="muted small">Own profile only</span>
            : (
              <div className="chip-list">
                {u.permissions.length
                  ? u.permissions.map((p) => <span key={p} className="chip">{p}</span>)
                  : <span className="muted small">View only</span>}
              </div>
            )}
      </td>
      <td>{u.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}</td>
      <td style={{ whiteSpace: "nowrap" }}>
        <button className="icon-btn" title="Edit" onClick={onEdit}><Pencil size={15} /></button>
        <button className="icon-btn" title="Issue temporary password" onClick={onReset}><KeyRound size={15} /></button>
        {u.id !== session.id && (
          <>
            <button className="btn ghost sm" onClick={onToggle}>
              {u.active ? "Disable" : "Enable"}
            </button>
            <button className="icon-btn danger" title="Delete" onClick={onDel}><Trash2 size={15} /></button>
          </>
        )}
      </td>
    </tr>
  );
}

// ── section wrapper ───────────────────────────────────────────────────────────

function Section({ icon: Icon, title, sub, count, tint, children, action, q, onQ, searchPlaceholder }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div className="row" style={{ gap: 10, alignItems: "center" }}>
          <span className={`stat-icon ${tint}`} style={{ width: 36, height: 36 }}>
            <Icon size={18} />
          </span>
          <div>
            <h2 style={{ margin: 0, fontSize: "1rem" }}>
              {title}
              <span className="muted" style={{ fontWeight: 400, marginLeft: 8, fontSize: "0.85rem" }}>
                ({count})
              </span>
            </h2>
            <div className="small muted">{sub}</div>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          {onQ && (
            <div className="search" style={{ margin: 0 }}>
              <Search size={14} />
              <input placeholder={searchPlaceholder || "Search…"} value={q} onChange={(e) => onQ(e.target.value)}
                style={{ width: 160 }} />
            </div>
          )}
          {action}
        </div>
      </div>
      <div className="card flush" style={{ overflowX: "auto" }}>
        {children}
      </div>
    </div>
  );
}

function EmptyRow({ cols, message }) {
  return (
    <tr>
      <td colSpan={cols} style={{ textAlign: "center", padding: "20px 0", color: "var(--muted)" }}>
        {message}
      </td>
    </tr>
  );
}

// ── students section — has grade/section filter ───────────────────────────────

function StudentSection({ students, session, actions, onAdd }) {
  const [filterGrade, setFilterGrade] = useState("");
  const [filterSection, setFilterSection] = useState("");
  const [q, setQ] = useState("");

  // Available grades from the actual data
  const availGrades = GRADES.filter((g) => students.some((u) => u.grade === g));
  // Available sections for the selected grade (or all sections if no grade selected)
  const availSections = [...new Set(
    students
      .filter((u) => !filterGrade || u.grade === filterGrade)
      .map((u) => u.section)
      .filter(Boolean)
  )].sort();

  const visible = students.filter((u) => {
    if (filterGrade && u.grade !== filterGrade) return false;
    if (filterSection && u.section !== filterSection) return false;
    if (q && !u.full_name.toLowerCase().includes(q.toLowerCase()) &&
            !u.username.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  const filterActive = filterGrade || filterSection || q;

  return (
    <div style={{ marginBottom: 28 }}>
      {/* Header */}
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div className="row" style={{ gap: 10, alignItems: "center" }}>
          <span className="stat-icon indigo" style={{ width: 36, height: 36 }}>
            <GraduationCap size={18} />
          </span>
          <div>
            <h2 style={{ margin: 0, fontSize: "1rem" }}>
              Students
              <span className="muted" style={{ fontWeight: 400, marginLeft: 8, fontSize: "0.85rem" }}>
                ({filterActive ? `${visible.length} of ${students.length}` : students.length})
              </span>
            </h2>
            <div className="small muted">Students can only view their own profile, marks and attendance</div>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <div className="search" style={{ margin: 0 }}>
            <Search size={14} />
            <input placeholder="Search students…" value={q} onChange={(e) => setQ(e.target.value)}
              style={{ width: 160 }} />
          </div>
          <button className="btn sm" onClick={onAdd}>
            <Plus size={14} /> Add student login
          </button>
        </div>
      </div>

      {/* Filters */}
      {students.length > 0 && (
        <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Filter size={14} style={{ color: "var(--muted)", flexShrink: 0 }} />
          {/* Grade filter */}
          <div className="tabs" style={{ margin: 0 }}>
            <button className={!filterGrade ? "on" : ""} onClick={() => { setFilterGrade(""); setFilterSection(""); }}>
              All classes
            </button>
            {availGrades.map((g) => (
              <button key={g}
                className={filterGrade === g ? "on" : ""}
                onClick={() => { setFilterGrade(g); setFilterSection(""); }}>
                {g === "LKG" || g === "UKG" ? g : `Class ${g}`}
              </button>
            ))}
          </div>
          {/* Section filter — only when a grade is selected and multiple sections exist */}
          {filterGrade && availSections.length > 1 && (
            <div className="tabs" style={{ margin: 0 }}>
              <button className={!filterSection ? "on" : ""} onClick={() => setFilterSection("")}>
                All sections
              </button>
              {availSections.map((s) => (
                <button key={s}
                  className={filterSection === s ? "on" : ""}
                  onClick={() => setFilterSection(s)}>
                  Section {s}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="card flush" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr><th>Student</th><th>Class</th><th>Access</th><th>Status</th><th /></tr>
          </thead>
          <tbody>
            {students.length === 0 && <EmptyRow cols={5} message="No student logins yet." />}
            {students.length > 0 && visible.length === 0 && (
              <EmptyRow cols={5} message="No students match this filter." />
            )}
            {visible.map((u) => {
              const link = profileLink(u);
              return (
                <tr key={u.id}>
                  <td>
                    <div className="row" style={{ gap: 6, alignItems: "center" }}>
                      <div>
                        <b>{u.full_name}</b>
                        <div className="small muted">{u.username}</div>
                      </div>
                      {link && (
                        <Link to={link} title="View profile"
                          style={{ color: "var(--primary)", opacity: 0.7, flexShrink: 0 }}>
                          <ExternalLink size={13} />
                        </Link>
                      )}
                    </div>
                  </td>
                  <td>
                    {u.grade
                      ? <span className="chip">{u.grade === "LKG" || u.grade === "UKG" ? u.grade : `Class ${u.grade}`}-{u.section}</span>
                      : <span className="muted small">–</span>}
                  </td>
                  <td><span className="muted small">Own profile only</span></td>
                  <td>{u.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="icon-btn" title="Edit" onClick={actions(u).onEdit}><Pencil size={15} /></button>
                    <button className="icon-btn" title="Issue temporary password" onClick={actions(u).onReset}><KeyRound size={15} /></button>
                    {u.id !== session.id && (
                      <>
                        <button className="btn ghost sm" onClick={actions(u).onToggle}>
                          {u.active ? "Disable" : "Enable"}
                        </button>
                        <button className="icon-btn danger" title="Delete" onClick={actions(u).onDel}><Trash2 size={15} /></button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const { session } = useAuth();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const [secret, setSecret] = useState(null);
  const [qAdmin, setQAdmin] = useState("");
  const [qStaff, setQStaff] = useState("");

  const state = useLoad(async () => {
    const [users, perms, students, staff] = await Promise.all([
      api("/users"),
      api("/permissions"),
      api("/students?page_size=500").catch(() => ({ items: [] })),
      api("/staff").catch(() => []),
    ]);
    return { users, perms, students: students.items, staff };
  }, [tick]);

  const reload = () => setTick((t) => t + 1);

  const actions = (u) => ({
    onEdit: () => setDlg({ type: "edit", u }),
    onReset: () => setDlg({ type: "reset", u }),
    onToggle: async () => {
      await api(`/users/${u.id}`, { method: "PUT", body: { active: !u.active } });
      reload();
    },
    onDel: () => setDlg({ type: "del", u }),
  });

  return (
    <>
      <PageHead
        title="Users & Access"
        sub="Manage logins for admins, staff and students. Each category has its own access rules."
      />

      <Async state={state}>
        {(d) => {
          const admins   = d.users.filter((u) => u.role === "admin");
          const staff    = d.users.filter((u) => u.role === "staff");
          const students = d.users.filter((u) => u.role === "student");

          const filt = (arr, q) => q
            ? arr.filter((u) => u.full_name.toLowerCase().includes(q.toLowerCase()) ||
                                u.username.toLowerCase().includes(q.toLowerCase()))
            : arr;

          return (
            <>
              {/* ── ADMINS ─────────────────────────────────────────────────── */}
              <Section
                icon={ShieldCheck}
                tint="bad"
                title="Admins"
                sub="Full access to everything — add carefully"
                count={admins.length}
                q={qAdmin} onQ={setQAdmin} searchPlaceholder="Search admins…"
                action={
                  <button className="btn sm" onClick={() => setDlg({ type: "add", role: "admin" })}>
                    <Plus size={14} /> Add admin
                  </button>
                }
              >
                <table>
                  <thead><tr><th>User</th><th>Access</th><th>Status</th><th /></tr></thead>
                  <tbody>
                    {admins.length === 0 && <EmptyRow cols={4} message="No admin accounts." />}
                    {admins.length > 0 && filt(admins, qAdmin).length === 0 && <EmptyRow cols={4} message={`No admins match "${qAdmin}".`} />}
                    {filt(admins, qAdmin).map((u) => <UserRow key={u.id} u={u} session={session} {...actions(u)} />)}
                  </tbody>
                </table>
              </Section>

              {/* ── STAFF ──────────────────────────────────────────────────── */}
              <Section
                icon={Users}
                tint="warn"
                title="Staff"
                sub="Teachers and non-teaching staff — grant only the permissions each person needs"
                count={staff.length}
                q={qStaff} onQ={setQStaff} searchPlaceholder="Search staff…"
                action={
                  <button className="btn sm" onClick={() => setDlg({ type: "add", role: "staff" })}>
                    <Plus size={14} /> Add staff login
                  </button>
                }
              >
                <table>
                  <thead><tr><th>User</th><th>Permissions</th><th>Status</th><th /></tr></thead>
                  <tbody>
                    {staff.length === 0 && <EmptyRow cols={4} message="No staff logins yet. Create one to give a staff member access." />}
                    {staff.length > 0 && filt(staff, qStaff).length === 0 && <EmptyRow cols={4} message={`No staff match "${qStaff}".`} />}
                    {filt(staff, qStaff).map((u) => <UserRow key={u.id} u={u} session={session} {...actions(u)} />)}
                  </tbody>
                </table>
              </Section>

              {/* ── STUDENTS ───────────────────────────────────────────────── */}
              <StudentSection
                students={students}
                session={session}
                actions={actions}
                onAdd={() => setDlg({ type: "add", role: "student" })}
              />

              {/* ── dialogs ──────────────────────────────────────────────── */}
              {(dlg?.type === "add" || dlg?.type === "edit") && (
                <UserForm
                  user={dlg.u}
                  perms={d.perms}
                  students={d.students}
                  staff={d.staff}
                  onClose={() => setDlg(null)}
                  onSaved={(created) => {
                    reload();
                    if (created) setSecret({ title: "User created", username: created.username, password: created.temp_password });
                  }}
                  defaultRole={dlg.role}
                />
              )}
              {dlg?.type === "reset" && (
                <Confirm
                  danger={false}
                  title="Issue temporary password"
                  message={`Issue a temporary password for ${dlg.u.username}? Hand it to them in person. They must set their own password the moment they sign in — nothing else will work until they do.`}
                  onClose={() => setDlg(null)}
                  onConfirm={async () => {
                    const r = await api(`/users/${dlg.u.id}/reset-password`, { method: "POST" });
                    setSecret({ title: "Temporary password issued", username: r.username, password: r.temp_password });
                  }}
                />
              )}
              {dlg?.type === "del" && (
                <Confirm
                  title="Delete login"
                  message={`Delete login for ${dlg.u.full_name} (${dlg.u.username})? Their student or staff record is kept — only the login is removed.`}
                  onClose={() => setDlg(null)}
                  onConfirm={async () => { await api(`/users/${dlg.u.id}`, { method: "DELETE" }); reload(); }}
                />
              )}
            </>
          );
        }}
      </Async>

      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
    </>
  );
}
