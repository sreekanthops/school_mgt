import { useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { PageHead } from "../components/ui.jsx";

export default function Account() {
  const { session } = useAuth();
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (f.new_password !== f.confirm) return setMsg({ bad: true, text: "New passwords do not match" });
    setBusy(true);
    setMsg(null);
    try {
      await api("/auth/password", { method: "POST", body: { current_password: f.current_password, new_password: f.new_password } });
      setMsg({ text: "Password updated." });
      setF({ current_password: "", new_password: "", confirm: "" });
    } catch (x) {
      setMsg({ bad: true, text: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead title="My Account" sub={`${session.name} · ${session.username} · ${session.role}`} />
      <div className="card" style={{ maxWidth: 440 }}>
        <h3 style={{ marginTop: 0 }}>Change password</h3>
        {msg && <div className={msg.bad ? "error" : "notice"}>{msg.text}</div>}
        <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
          <div className="field"><label htmlFor="cp">Current password</label>
            <input id="cp" type="password" autoComplete="current-password" required value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} /></div>
          <div className="field"><label htmlFor="np">New password (min 10 characters)</label>
            <input id="np" type="password" autoComplete="new-password" required minLength={10} maxLength={128} value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} /></div>
          <div className="field"><label htmlFor="cf">Confirm new password</label>
            <input id="cf" type="password" autoComplete="new-password" required value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></div>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Update password"}</button>
        </form>
      </div>
    </>
  );
}
