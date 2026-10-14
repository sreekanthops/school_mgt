import { useState } from "react";
import { KeyRound, Plus, Power, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { Async, Badge, Confirm, FormModal, PageHead, Secret, useLoad } from "../components/ui.jsx";

const fields = [
  { key: "name", label: "School name", required: true, full: true },
  { key: "owner_name", label: "Owner full name", required: true },
  { key: "owner_username", label: "Owner username", required: true },
];

export default function Schools() {
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const [secret, setSecret] = useState(null);
  const state = useLoad(() => api("/schools"), [tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <>
      <PageHead title="Schools" sub="Each school is fully isolated. Create one and hand its owner the login.">
        <button className="btn" onClick={() => setDlg({ type: "add" })}><Plus size={16} /> New school</button>
      </PageHead>
      <Async state={state}>
        {(rows) => (
          <div className="card flush" style={{ overflowX: "auto" }}>
            <table>
              <thead><tr><th>School</th><th>Owner</th><th>Students</th><th>Staff</th><th>Users</th><th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td><b>{s.name}</b><div className="small muted">Created {s.created_at.slice(0, 10)}</div></td>
                    <td>{s.owner ? <>{s.owner.name}<div className="small muted">{s.owner.username}</div></> : "–"}</td>
                    <td>{s.students}</td><td>{s.staff}</td><td>{s.users}</td>
                    <td>{s.active ? <Badge kind="good">Active</Badge> : <Badge kind="gray">Disabled</Badge>}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="icon-btn" title="Reset owner password" onClick={() => setDlg({ type: "reset", s })}><KeyRound size={15} /></button>
                      <button className="icon-btn" title={s.active ? "Disable" : "Enable"} onClick={() => setDlg({ type: "toggle", s })}><Power size={15} /></button>
                      <button className="icon-btn danger" title="Delete" onClick={() => setDlg({ type: "del", s })}><Trash2 size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Async>
      {dlg?.type === "add" && (
        <FormModal title="Create school" fields={fields} submitLabel="Create" onClose={() => setDlg(null)}
          onSubmit={async (b) => {
            const r = await api("/schools", { method: "POST", body: b });
            setSecret({ title: `${r.school.name} created`, username: r.owner.username, password: r.owner.temp_password });
            reload();
          }} />
      )}
      {dlg?.type === "reset" && (
        <Confirm danger={false} title="Reset owner password" message={`Generate a new temporary password for the owner of ${dlg.s.name}?`}
          onClose={() => setDlg(null)} onConfirm={async () => {
            const r = await api(`/schools/${dlg.s.id}/owner/reset-password`, { method: "POST" });
            setSecret({ title: "Password reset", username: r.username, password: r.temp_password });
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
