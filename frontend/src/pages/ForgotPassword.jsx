import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ArrowLeft, KeyRound, LifeBuoy, Lock, Mail, ShieldAlert, UserCheck } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

/**
 * Forgot-password — three tiers.
 *
 * Tier 1 (all users):  Enter your Login ID → answer the 3 questions YOU set at first login
 *                       → if all 3 match → choose a new password.
 *                       After 5 wrong attempts the account is locked for a cooldown period.
 *
 * Tier 2 (all users):  Still can't get in? → contact IT / school admin in person.
 *                       They issue a temporary password from Users & Access.
 *                       On next sign-in you are forced to choose your own password immediately.
 *
 * Tier 3 (owner only): If you are the school owner → enter the Gmail address you saved in
 *                       My Account → a one-time reset link (15 min) is emailed to you.
 */
export default function ForgotPassword() {
  const { session } = useAuth();

  // Tier 1 state machine: "id" → "questions" → "done"
  const [step, setStep] = useState("id");
  const [username, setUsername] = useState("");
  const [qs, setQs] = useState([]);
  const [answers, setAnswers] = useState(["", "", ""]);
  const [pw, setPw] = useState({ a: "", b: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // Tier 3 state machine
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerStep, setOwnerStep] = useState("idle"); // idle | sent
  const [ownerErr, setOwnerErr] = useState("");
  const [ownerBusy, setOwnerBusy] = useState(false);

  if (session) return <Navigate to="/" replace />;

  // ── Tier 1 handlers ──────────────────────────────────────────────────────────
  async function ask(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const r = await api("/auth/forgot/questions", {
        method: "POST",
        body: { username: username.trim() },
      });
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
      await api("/auth/forgot/reset", {
        method: "POST",
        body: { username: username.trim(), answers, new_password: pw.a },
      });
      setStep("done");
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  // ── Tier 3 handler ───────────────────────────────────────────────────────────
  async function sendOwnerEmail(e) {
    e.preventDefault();
    setOwnerBusy(true);
    setOwnerErr("");
    try {
      await api("/auth/forgot/owner-email", {
        method: "POST",
        body: { email: ownerEmail.trim(), base_url: window.location.origin },
      });
      setOwnerStep("sent");
    } catch (x) {
      setOwnerErr(x.message);
    } finally {
      setOwnerBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      {/* ── Left panel: instructions ─────────────────────────────────────────── */}
      <div className="login-art">
        <span className="stat-icon indigo" style={{ width: 56, height: 56 }}>
          <LifeBuoy size={30} />
        </span>
        <h1>Forgot your password?</h1>

        <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 8 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span className="stat-icon" style={{ width: 32, height: 32, flexShrink: 0, fontSize: 13, fontWeight: 700, background: "rgba(255,255,255,0.15)" }}>1</span>
            <div>
              <b>Answer your security questions</b>
              <p style={{ opacity: 0.85, margin: "4px 0 0" }}>
                Enter your Login ID. You will be shown the exact three questions <em>you</em> answered
                when you first set up your account. All three must match to reset your password.
                After 5 wrong attempts the form locks for a cooldown period.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span className="stat-icon" style={{ width: 32, height: 32, flexShrink: 0, fontSize: 13, fontWeight: 700, background: "rgba(255,255,255,0.15)" }}>2</span>
            <div>
              <b>Ask the school admin / IT for a temporary password</b>
              <p style={{ opacity: 0.85, margin: "4px 0 0" }}>
                If you cannot answer the questions, contact the school's admin office or IT department
                in person. They will issue a temporary password from the Users &amp; Access page.
                The moment you sign in with it you will be prompted to choose your own password —
                this is mandatory and cannot be skipped.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <span className="stat-icon" style={{ width: 32, height: 32, flexShrink: 0, fontSize: 13, fontWeight: 700, background: "rgba(255,255,255,0.15)" }}>3</span>
            <div>
              <b>School owners: reset via Gmail</b>
              <p style={{ opacity: 0.85, margin: "4px 0 0" }}>
                If you are the school owner and you saved a Gmail recovery address in My Account,
                use the form at the bottom of this page to receive a one-time reset link (valid 15 min).
                If you have not saved one, the platform support team can reset it for you.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Right panel: forms ───────────────────────────────────────────────── */}
      <div className="login-form">
        <div className="login-card">
          <Link to="/login" className="backlink"><ArrowLeft size={14} /> Back to sign in</Link>

          {/* ── TIER 1: enter login ID ─────────────────────────────────────── */}
          {step === "id" && (
            <form onSubmit={ask}>
              <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <UserCheck size={20} /> Step 1 — your security questions
              </h1>
              <p className="muted" style={{ marginBottom: 18, marginTop: 4 }}>
                Enter your Login ID. You will be shown the three questions <b>you</b> set up —
                only you know the answers.
              </p>
              {err && <div className="error">{err}</div>}
              <div className="field" style={{ marginBottom: 18 }}>
                <label htmlFor="fu">Login ID</label>
                <input id="fu" value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username" required autoFocus />
              </div>
              <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
                {busy ? "Please wait…" : "Continue"}
              </button>
            </form>
          )}

          {/* ── TIER 1: answer questions ───────────────────────────────────── */}
          {step === "questions" && (
            <form onSubmit={reset}>
              <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ShieldAlert size={20} /> Your security questions
              </h1>
              <p className="muted" style={{ marginBottom: 16, marginTop: 4 }}>
                These are the three questions <b>you</b> answered when you first set up your account.
                Answers are not case-sensitive; punctuation and extra spaces are ignored.
              </p>
              {err && <div className="error">{err}</div>}
              {qs.map((q, i) => (
                <div className="field" style={{ marginBottom: 12 }} key={q.id}>
                  <label htmlFor={`fq${i}`}>{i + 1}. {q.text}</label>
                  <input id={`fq${i}`} value={answers[i]} maxLength={80} required autoComplete="off"
                    onChange={(e) => setAnswers(answers.map((a, j) => j === i ? e.target.value : a))} />
                </div>
              ))}
              <div className="field" style={{ marginBottom: 12 }}>
                <label htmlFor="fp1">New password (min 10 characters)</label>
                <input id="fp1" type="password" minLength={10} maxLength={128} required
                  autoComplete="new-password" value={pw.a}
                  onChange={(e) => setPw({ ...pw, a: e.target.value })} />
              </div>
              <div className="field" style={{ marginBottom: 18 }}>
                <label htmlFor="fp2">Confirm new password</label>
                <input id="fp2" type="password" required autoComplete="new-password" value={pw.b}
                  onChange={(e) => setPw({ ...pw, b: e.target.value })} />
              </div>
              <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
                <KeyRound size={15} /> {busy ? "Checking…" : "Reset my password"}
              </button>
              <button type="button" className="btn ghost" style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
                onClick={() => { setStep("id"); setErr(""); setAnswers(["", "", ""]); setPw({ a: "", b: "" }); }}>
                ← Try a different Login ID
              </button>
            </form>
          )}

          {/* ── TIER 1: success ────────────────────────────────────────────── */}
          {step === "done" && (
            <div>
              <h1>Password changed ✓</h1>
              <p className="muted">You can now sign in with your new password.</p>
              <Link className="btn" to="/login" style={{ width: "100%", justifyContent: "center" }}>
                Go to sign in
              </Link>
            </div>
          )}

          {/* ── TIER 2: ask IT / admin ─────────────────────────────────────── */}
          {step !== "done" && (
            <div style={{ marginTop: 28, borderTop: "1px solid var(--border,#e5e7eb)", paddingTop: 22 }}>
              <h2 style={{ fontSize: "0.95rem", marginTop: 0, display: "flex", alignItems: "center", gap: 6 }}>
                <Lock size={15} /> Still can't get in? Ask IT / admin for a temp password
              </h2>
              <p className="small muted" style={{ margin: "0 0 10px" }}>
                Contact the school's admin office or IT department in person and ask them to issue you
                a <b>temporary password</b> from the <em>Users &amp; Access</em> page.
                When you sign in with it you <b>must</b> choose your own password immediately —
                you cannot access anything else until you do.
              </p>
              <div className="notice" style={{ fontSize: 13 }}>
                <b>Important:</b> the admin can only reset passwords for staff and student accounts —
                not for the school owner. Owners must use the Gmail reset below or contact platform support.
              </div>
            </div>
          )}

          {/* ── TIER 3: owner Gmail reset ──────────────────────────────────── */}
          {step !== "done" && (
            <div style={{ marginTop: 24, borderTop: "1px solid var(--border,#e5e7eb)", paddingTop: 22 }}>
              <h2 style={{ fontSize: "0.95rem", marginTop: 0, display: "flex", alignItems: "center", gap: 6 }}>
                <Mail size={15} /> School owner? Reset via Gmail
              </h2>
              <p className="small muted" style={{ margin: "0 0 12px" }}>
                Only works if you saved a Gmail recovery address in <em>My Account → Gmail recovery</em>.
                A one-time reset link valid for 15 minutes will be sent to that address.
              </p>

              {ownerStep === "idle" && (
                <form onSubmit={sendOwnerEmail}>
                  {ownerErr && <div className="error" style={{ marginBottom: 10 }}>{ownerErr}</div>}
                  <div className="field" style={{ marginBottom: 12 }}>
                    <label htmlFor="oe">Your configured Gmail address</label>
                    <input id="oe" type="email" value={ownerEmail} required placeholder="you@gmail.com"
                      onChange={(e) => setOwnerEmail(e.target.value)} autoComplete="email" />
                  </div>
                  <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={ownerBusy}>
                    <Mail size={15} /> {ownerBusy ? "Sending…" : "Send reset link"}
                  </button>
                </form>
              )}

              {ownerStep === "sent" && (
                <div>
                  <div className="notice">
                    If that address is registered as an owner recovery email, a reset link has been sent.
                    Check your inbox (and spam folder) — the link expires in 15 minutes.
                  </div>
                  <p className="small muted" style={{ marginTop: 10 }}>
                    Didn't receive it? Make sure you entered the exact address saved in My Account,
                    or contact the platform support team.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
