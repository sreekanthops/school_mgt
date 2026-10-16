import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, KeyRound, LifeBuoy } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

/**
 * Landing page for the owner Gmail reset link.
 * URL: /reset-owner-password?token=<token>
 * The token comes from the email sent by POST /auth/forgot/owner-email.
 * Submitting the form calls POST /auth/forgot/owner-confirm.
 */
export default function ResetOwnerPassword() {
  const { session } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token") || "";

  const [pw, setPw] = useState({ a: "", b: "" });
  const [step, setStep] = useState(token ? "form" : "invalid"); // invalid | form | done
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) setStep("invalid");
  }, [token]);

  if (session) return <Navigate to="/" replace />;

  async function submit(e) {
    e.preventDefault();
    if (pw.a !== pw.b) return setErr("The two passwords do not match");
    setBusy(true);
    setErr("");
    try {
      await api("/auth/forgot/owner-confirm", { method: "POST", body: { token, new_password: pw.a } });
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
        <h1>Set a new password</h1>
        <p style={{ opacity: 0.85 }}>
          You followed a one-time link sent to your Gmail recovery address.
          Choose a strong password — at least 10 characters. The link is valid for 15 minutes.
        </p>
      </div>

      <div className="login-form">
        <div className="login-card">
          <Link to="/login" className="backlink"><ArrowLeft size={14} /> Back to sign in</Link>

          {step === "invalid" && (
            <div>
              <h1>Invalid link</h1>
              <p className="muted">This reset link is missing a token. Please go back to the forgot-password page and request a new link.</p>
              <Link className="btn" to="/forgot" style={{ width: "100%", justifyContent: "center" }}>Forgot password</Link>
            </div>
          )}

          {step === "form" && (
            <form onSubmit={submit}>
              <h1>Choose a new password</h1>
              <div className="muted" style={{ marginBottom: 16 }}>This link expires 15 minutes after it was sent.</div>
              {err && <div className="error">{err}</div>}
              <div className="field" style={{ marginBottom: 12 }}>
                <label htmlFor="rp1">New password (min 10 characters)</label>
                <input id="rp1" type="password" minLength={10} maxLength={128} required autoComplete="new-password"
                  value={pw.a} onChange={(e) => setPw({ ...pw, a: e.target.value })} autoFocus />
              </div>
              <div className="field" style={{ marginBottom: 18 }}>
                <label htmlFor="rp2">Confirm new password</label>
                <input id="rp2" type="password" required autoComplete="new-password"
                  value={pw.b} onChange={(e) => setPw({ ...pw, b: e.target.value })} />
              </div>
              <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
                <KeyRound size={15} /> {busy ? "Saving…" : "Set new password"}
              </button>
            </form>
          )}

          {step === "done" && (
            <div>
              <h1>Password changed</h1>
              <p className="muted">Your owner password has been updated. You can now sign in with your new password.</p>
              <Link className="btn" to="/login" style={{ width: "100%", justifyContent: "center" }}>Go to sign in</Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
