import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { session, login } = useAuth();
  const nav = useNavigate();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (session) return <Navigate to="/" replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await login(u, p);
      nav("/");
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h1>Sunrise Public School</h1>
        <div className="muted" style={{ marginBottom: 16 }}>Sign in to the management suite</div>
        {err && <div className="error">{err}</div>}
        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="u">Username</label>
          <input id="u" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" required />
        </div>
        <div className="field" style={{ marginBottom: 16 }}>
          <label htmlFor="p">Password</label>
          <input id="p" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
        </div>
        <button className="btn" style={{ width: "100%" }} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
