import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ArrowLeft, KeyRound, LifeBuoy, Lock, Mail, ShieldAlert } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

/**
 * Forgot-password — three tiers.
 *
 * Tier 1 (all users):  Enter your Login ID + pick the 3 questions YOU set at first login
 *                       and type in your answers — all in one form, no separate step to
 *                       "fetch" questions (avoids leaking which accounts exist).
 *                       If all 3 match you can choose a new password immediately.
 *                       After 5 wrong attempts the account is locked for a cooldown period.
 *
 * Tier 2 (all users):  Still can't get in? → contact IT / school admin in person.
 *                       They issue a temporary password from Users & Access.
 *                       On next sign-in you are forced to choose your own password immediately.
 *
 * Tier 3 (owner only): If you are the school owner → enter the Gmail address you saved in
 *                       My Account → a one-time reset link (15 min) is emailed to you.
 */

/** All 12 questions in the bank — must match backend QUESTIONS list order. */
const QUESTIONS = [
  "What was the name of your first pet, or a pet you loved as a child?",
  "What was the name of the street you lived on as a child?",
  "What is the first name of your childhood best friend?",
  "In which town or village did your mother grow up?",
  "What was the name of the first school you attended?",
  "What is the surname of your favourite teacher?",
  "What was the first film you watched in a cinema?",
  "What is the title of the first book you remember loving?",
  "What is the first name of your paternal grandmother?",
  "What was your favourite game to play as a child?",
  "What was the first dish you learned to cook, or loved eating as a child?",
  "What was the name of your favourite toy or cartoon character as a child?",
];

const DEFAULT_IDS = [0, 1, 2]; // initial placeholder selections

export default function ForgotPassword() {
  const { session } = useAuth();

  // Tier 1 — single combined form
  const [step, setStep] = useState("form"); // "form" | "done"
  const [username, setUsername] = useState("");
  // Each slot: { id: questionIndex, answer: string }
  const [slots, setSlots] = useState(DEFAULT_IDS.map((id) => ({ id, answer: "" })));
  const [pw, setPw] = useState({ a: "", b: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // Tier 3 state
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerStep, setOwnerStep] = useState("idle"); // "idle" | "sent"
  const [ownerErr, setOwnerErr] = useState("");
  const [ownerBusy, setOwnerBusy] = useState(false);

  if (session) return <Navigate to="/" replace />;

  // ── helpers ──────────────────────────────────────────────────────────────────
  function setSlotId(i, id) {
    setSlots(slots.map((s, j) => (j === i ? { ...s, id: Number(id) } : s)));
  }
  function setSlotAnswer(i, answer) {
    setSlots(slots.map((s, j) => (j === i ? { ...s, answer } : s)));
  }

  /** Questions available for a given slot (not selected in any other slot). */
  function available(slotIndex) {
    const taken = new Set(slots.map((s, j) => (j !== slotIndex ? s.id : null)));
    return QUESTIONS.map((text, id) => ({ id, text })).filter((q) => !taken.has(q.id));
  }

  // ── Tier 1 submit ─────────────────────────────────────────────────────────────
  async function submit(e) {
    e.preventDefault();
    if (pw.a !== pw.b) return setErr("The two passwords do not match.");
    const ids = slots.map((s) => s.id);
    if (new Set(ids).size !== 3) return setErr("Please choose three different questions.");
    setBusy(true);
    setErr("");
    try {
      await api("/auth/forgot/reset", {
        method: "POST",
        body: {
          username: username.trim(),
          answers: slots.map((s) => ({ id: s.id, answer: s.answer })),
          new_password: pw.a,
        },
      });
      setStep("done");
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  // ── Tier 3 handler ────────────────────────────────────────────────────────────
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
                Enter your Login ID, pick the three questions <em>you</em> chose when you first set
                up your account, type in your answers, and set a new password — all in one go.
                Answers are not case-sensitive and punctuation is ignored.
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
                The moment you sign in with it you <em>must</em> choose your own password —
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

          {/* ── TIER 1: combined single form ──────────────────────────────────── */}
          {step === "form" && (
            <form onSubmit={submit}>
              <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ShieldAlert size={20} /> Reset your password
              </h1>
              <p className="muted" style={{ marginBottom: 16, marginTop: 4 }}>
                Enter your Login ID, select the three questions <b>you</b> answered when you first
                set up your account, fill in the answers, and choose a new password.
              </p>

              {err && <div className="error">{err}</div>}

              <div className="field" style={{ marginBottom: 14 }}>
                <label htmlFor="fu">Login ID</label>
                <input id="fu" value={username} required autoFocus autoComplete="username"
                  onChange={(e) => setUsername(e.target.value)} />
              </div>

              {slots.map((slot, i) => (
                <div key={i} style={{ marginBottom: 12, padding: "10px 12px", background: "var(--surface,#f7f8fa)", borderRadius: 6, border: "1px solid var(--border,#e5e7eb)" }}>
                  <div className="field" style={{ marginBottom: 8 }}>
                    <label htmlFor={`qsel${i}`}>Question {i + 1}</label>
                    <select id={`qsel${i}`} value={slot.id} required
                      onChange={(e) => setSlotId(i, e.target.value)}
                      style={{ width: "100%" }}>
                      {available(i).map((q) => (
                        <option key={q.id} value={q.id}>{q.text}</option>
                      ))}
                      {/* Keep the current selection visible even if it'd be "taken" by another slot */}
                      {!available(i).find((q) => q.id === slot.id) && (
                        <option value={slot.id}>{QUESTIONS[slot.id]}</option>
                      )}
                    </select>
                  </div>
                  <div className="field" style={{ marginBottom: 0 }}>
                    <label htmlFor={`ans${i}`}>Your answer</label>
                    <input id={`ans${i}`} value={slot.answer} required maxLength={80}
                      autoComplete="off"
                      onChange={(e) => setSlotAnswer(i, e.target.value)} />
                  </div>
                </div>
              ))}

              <div className="field" style={{ marginBottom: 10, marginTop: 4 }}>
                <label htmlFor="fp1">New password (min 10 characters)</label>
                <input id="fp1" type="password" minLength={10} maxLength={128} required
                  autoComplete="new-password" value={pw.a}
                  onChange={(e) => setPw({ ...pw, a: e.target.value })} />
              </div>
              <div className="field" style={{ marginBottom: 16 }}>
                <label htmlFor="fp2">Confirm new password</label>
                <input id="fp2" type="password" required autoComplete="new-password" value={pw.b}
                  onChange={(e) => setPw({ ...pw, b: e.target.value })} />
              </div>
              <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
                <KeyRound size={15} /> {busy ? "Checking…" : "Reset my password"}
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
                Contact the school's admin office or IT department <b>in person</b> and ask them to
                issue you a <b>temporary password</b> from the <em>Users &amp; Access</em> page.
                When you sign in with it you <b>must</b> choose your own password immediately —
                you cannot access anything else until you do.
              </p>
              <div className="notice" style={{ fontSize: 13 }}>
                <b>Note:</b> the admin can only reset passwords for staff and student accounts —
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
                Only works if you saved a Gmail recovery address in <em>My Account → Gmail recovery</em>
                before forgetting your password. A one-time reset link valid for 15 minutes will be sent.
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
