import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ArrowLeft, KeyRound, LifeBuoy } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

export default function ForgotPassword() {
  const { session } = useAuth();
  const [step, setStep] = useState("id"); // id -> questions -> done
  const [username, setUsername] = useState("");
  const [qs, setQs] = useState([]);
  const [answers, setAnswers] = useState(["", "", ""]);
  const [pw, setPw] = useState({ a: "", b: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (session) return <Navigate to="/" replace />;

  async function ask(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const r = await api("/auth/forgot/questions", { method: "POST", body: { username: username.trim() } });
      setQs(r.questions);
      setStep("questions");
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  async function reset(e) {
    e.preventDefault();
    if (pw.a !== pw.b) return setErr("The two passwords do not match");
    setBusy(true);
    setErr("");
    try {
      await api("/auth/forgot/reset", { method: "POST", body: { username: username.trim(), answers, new_password: pw.a } });
      setStep("done");
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-art">
        <span className="stat-icon indigo" style={{ width: 56, height: 56 }}><LifeBuoy size={30} /></span>
        <h1>Forgot your password?</h1>
        <p style={{ opacity: 0.85 }}>Answer the three security questions you chose when you set up your account and pick a new password.</p>
        <p style={{ opacity: 0.85 }}>Can't answer them? Visit or call your school's <b>admin office or IT department</b>. They will give you a temporary password in person, and you will choose your own when you sign in.</p>
      </div>
      <div className="login-form">
        <div className="login-card">
          <Link to="/login" className="backlink"><ArrowLeft size={14} /> Back to sign in</Link>
          {step === "id" && (
            <form onSubmit={ask}>
              <h1>Reset password</h1>
              <div className="muted" style={{ marginBottom: 20 }}>Enter your Login ID</div>
              {err && <div className="error">{err}</div>}
              <div className="field" style={{ marginBottom: 18 }}>
                <label htmlFor="fu">Login ID</label>
                <input id="fu" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus />
              </div>
              <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>{busy ? "Please wait…" : "Continue"}</button>
            </form>
          )}
          {step === "questions" && (
            <form onSubmit={reset}>
              <h1>Your security questions</h1>
              <div className="muted" style={{ marginBottom: 16 }}>Answer all three. Capital letters and punctuation don't matter.</div>
              {err && <div className="error">{err}</div>}
              {qs.map((q, i) => (
                <div className="field" style={{ marginBottom: 12 }} key={q.id}>
                  <label htmlFor={`fq${i}`}>{i + 1}. {q.text}</label>
                  <input id={`fq${i}`} value={answers[i]} maxLength={80} required autoComplete="off"
                    onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))} />
                </div>
              ))}
              <div className="field" style={{ marginBottom: 12 }}>
                <label htmlFor="fp1">New password (min 10 characters)</label>
                <input id="fp1" type="password" minLength={10} maxLength={128} required autoComplete="new-password" value={pw.a} onChange={(e) => setPw({ ...pw, a: e.target.value })} />
              </div>
              <div className="field" style={{ marginBottom: 18 }}>
                <label htmlFor="fp2">Confirm new password</label>
                <input id="fp2" type="password" required autoComplete="new-password" value={pw.b} onChange={(e) => setPw({ ...pw, b: e.target.value })} />
              </div>
              <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}><KeyRound size={15} /> {busy ? "Checking…" : "Reset password"}</button>
              <p className="small muted" style={{ marginTop: 12 }}>Still stuck? Ask the school admin or IT department for a temporary password.</p>
            </form>
          )}
          {step === "done" && (
            <div>
              <h1>Password changed</h1>
              <p className="muted">You can now sign in with your new password.</p>
              <Link className="btn" to="/login" style={{ width: "100%", justifyContent: "center" }}>Go to sign in</Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
