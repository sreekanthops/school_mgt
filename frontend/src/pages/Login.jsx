import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { GraduationCap, ShieldCheck, Users, BookOpen, Sparkles } from "lucide-react";
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
      await login(u.trim(), p);
      nav("/");
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-wrap">
      <div className="login-art">
        <span className="stat-icon indigo" style={{ width: 56, height: 56 }}><GraduationCap size={30} /></span>
        <h1>One platform for every school.</h1>
        <ul style={{ listStyle: "none", padding: 0 }}>
          <li className="row"><Users size={18} /> Students, staff and parents in one place</li>
          <li className="row"><BookOpen size={18} /> Subjects, chapters, marks and fees</li>
          <li className="row"><ShieldCheck size={18} /> Each school's data is fully isolated</li>
          <li className="row"><Sparkles size={18} /> AI assistant that answers from your data</li>
        </ul>
      </div>
      <div className="login-form">
        <form className="login-card" onSubmit={submit}>
          <h1>Welcome back</h1>
          <div className="muted" style={{ marginBottom: 20 }}>Sign in to continue</div>
          {err && <div className="error">{err}</div>}
          <div className="field" style={{ marginBottom: 12 }}>
            <label htmlFor="u">Login ID</label>
            <input id="u" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" required autoFocus />
          </div>
          <div className="field" style={{ marginBottom: 18 }}>
            <label htmlFor="p">Password</label>
            <input id="p" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
          </div>
          <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          <div style={{ textAlign: "center", marginTop: 14 }}><Link to="/forgot">Forgot password?</Link></div>
        </form>
      </div>
    </div>
  );
}
