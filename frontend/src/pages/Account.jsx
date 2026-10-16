import { useState } from "react";
import { CheckCircle, Circle, Mail, ShieldCheck } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, PageHead, useLoad } from "../components/ui.jsx";

// ─── Step wrapper ──────────────────────────────────────────────────────────────
/** A numbered step card in the setup stepper. */
function SetupStep({ num, title, status, children }) {
  // status: "active" | "done" | "locked"
  return (
    <div className={`setup-step ${status}`}>
      <div className="setup-step-head">
        <div className="setup-step-num">{status === "done" ? "✓" : num}</div>
        <h3>{title}</h3>
        <span className="setup-step-status" style={{ color: status === "done" ? "var(--good)" : status === "active" ? "var(--primary)" : "var(--muted)" }}>
          {status === "done" ? "Complete" : status === "active" ? "Action required" : "Waiting…"}
        </span>
      </div>
      {status !== "locked" && <div className="setup-step-body">{children}</div>}
    </div>
  );
}

// ─── Password card ─────────────────────────────────────────────────────────────
function PasswordCard({ forced }) {
  const { refresh } = useAuth();
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
      await refresh();
    } catch (x) {
      setMsg({ bad: true, text: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 420 }}>
      {forced && (
        <p className="muted" style={{ marginTop: 0 }}>
          You signed in with a temporary password set by the admin.
          Enter it below as the current password, then choose your own to continue.
        </p>
      )}
      {msg && <div className={msg.bad ? "error" : "notice"}>{msg.text}</div>}
      <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
        <div className="field">
          <label htmlFor="cp">{forced ? "Temporary password" : "Current password"}</label>
          <input id="cp" type="password" autoComplete="current-password" required autoFocus={forced}
            value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="np">New password (min 10 characters)</label>
          <input id="np" type="password" autoComplete="new-password" required minLength={10} maxLength={128}
            value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="cf">Confirm new password</label>
          <input id="cf" type="password" autoComplete="new-password" required
            value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} />
        </div>
        <div><button className="btn" disabled={busy}>{busy ? "Saving…" : forced ? "Set my password" : "Update password"}</button></div>
      </form>
    </div>
  );
}

// ─── Recovery questions card ───────────────────────────────────────────────────
function RecoveryCard({ mandatory }) {
  const { refresh } = useAuth();
  const [tick, setTick] = useState(0);
  const state = useLoad(() => api("/auth/recovery/setup"), [tick]);
  const [answers, setAnswers] = useState(["", "", ""]);
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  async function save(e, qs) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api("/auth/recovery/setup", {
        method: "POST",
        body: { current_password: pw, answers: qs.map((q, i) => ({ id: q.id, answer: answers[i] })) },
      });
      setMsg({ text: "Saved. Remember these answers — you will be asked the same three questions if you ever forget your password." });
      setAnswers(["", "", ""]);
      setPw("");
      await refresh();
      setTick((t) => t + 1);
    } catch (x) {
      setMsg({ bad: true, text: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Async state={state}>
      {(d) => (
        <div style={{ maxWidth: 520 }}>
          {!mandatory && (
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                <ShieldCheck size={14} style={{ verticalAlign: -2 }} />{" "}
                {d.configured
                  ? "Questions are set up. Change them below if you want different ones."
                  : "Not set up yet."}
              </span>
              {d.configured ? <Badge kind="good">Set up</Badge> : <Badge kind="warn">Not set up</Badge>}
            </div>
          )}
          {mandatory && !d.configured && (
            <p className="muted" style={{ marginTop: 0 }}>
              Answer these three questions and save them now.
              If you ever forget your password you can reset it yourself by answering the same questions.
            </p>
          )}
          {msg && <div className={msg.bad ? "error" : "notice"}>{msg.text}</div>}
          <form onSubmit={(e) => save(e, d.questions)} className="grid" style={{ gap: 12 }}>
            {d.questions.map((q, i) => (
              <div className="field" key={q.id}>
                <label htmlFor={`rq${i}`}>{i + 1}. {q.text}</label>
                <input id={`rq${i}`} value={answers[i]} maxLength={80} required autoComplete="off"
                  onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))} />
              </div>
            ))}
            <div className="field">
              <label htmlFor="rpw">Your current password (to confirm it's you)</label>
              <input id="rpw" type="password" autoComplete="current-password" required
                value={pw} onChange={(e) => setPw(e.target.value)} />
            </div>
            <div className="row">
              <button className="btn" disabled={busy}>
                {busy ? "Saving…" : d.configured ? "Replace questions" : "Save answers"}
              </button>
              <button type="button" className="btn ghost" onClick={() => { setAnswers(["", "", ""]); setTick((t) => t + 1); }}>
                Show different questions
              </button>
            </div>
            <p className="small muted" style={{ margin: 0 }}>
              Answers are stored scrambled (hashed) and cannot be read by anyone. Capital letters and punctuation don't matter.
            </p>
          </form>
        </div>
      )}
    </Async>
  );
}

// ─── Gmail recovery card (owner only) ─────────────────────────────────────────
function GmailRecoveryCard() {
  const [tick, setTick] = useState(0);
  const state = useLoad(() => api("/auth/recovery/email"), [tick]);
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api("/auth/recovery/email", { method: "PUT", body: { email } });
      setMsg({ text: "Gmail recovery address saved. You can use it on the forgot-password page if you ever cannot answer your security questions." });
      setEmail("");
      setTick((t) => t + 1);
    } catch (x) {
      setMsg({ bad: true, text: x.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Async state={state}>
      {(d) => (
        <div className="card" style={{ maxWidth: 520 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}><Mail size={17} style={{ verticalAlign: -3 }} /> Gmail password recovery</h3>
            {d.configured ? <Badge kind="good">Configured</Badge> : <Badge kind="warn">Not configured</Badge>}
          </div>
          {!d.smtp_enabled && (
            <div className="notice" style={{ marginTop: 10 }}>
              The platform team has not enabled email delivery yet. You can still save your Gmail address here — it will work once SMTP is switched on.
            </div>
          )}
          <p className="muted" style={{ marginTop: 10 }}>
            {d.configured
              ? "A Gmail recovery address is already saved. Enter a new address below to replace it."
              : "Save your personal Gmail address. If you forget your password and cannot answer the security questions, open the forgot-password page, choose \"I am the school owner\", enter this address, and a reset link will be sent."}
          </p>
          {msg && <div className={msg.bad ? "error" : "notice"}>{msg.text}</div>}
          <form onSubmit={save} className="grid" style={{ gap: 12, marginTop: 8 }}>
            <div className="field">
              <label htmlFor="re-email">Gmail address</label>
              <input id="re-email" type="email" value={email} required placeholder="you@gmail.com"
                onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Saving…" : d.configured ? "Update address" : "Save address"}</button>
          </form>
          <p className="small muted" style={{ marginTop: 8 }}>
            Only this Gmail address can trigger a reset link for your account. If you lose access to it too, contact the platform support team.
          </p>
        </div>
      )}
    </Async>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────
export default function Account() {
  const { session } = useAuth();
  const mustChangePassword = !!session.must_change;
  const mustSetupRecovery = !!session.must_setup_recovery;
  const onboarding = mustChangePassword || mustSetupRecovery;
  const isOwner = session.role === "admin";

  return (
    <>
      <PageHead title="My Account" sub={`${session.name} · ${session.username} · ${session.role}`} />

      {/* ── Mandatory onboarding stepper ─────────────────────────────────── */}
      {onboarding && (
        <div className="error" role="alert" style={{ marginBottom: 20 }}>
          {mustChangePassword
            ? "Complete Step 1 and Step 2 below before you can access the rest of the system."
            : "Complete Step 2 below before you can access the rest of the system."}
        </div>
      )}

      {onboarding ? (
        <div className="setup-stepper" style={{ maxWidth: 600 }}>
          {/* Step 1 — change password */}
          <SetupStep
            num={1}
            title="Set your own password"
            status={mustChangePassword ? "active" : "done"}
          >
            <PasswordCard forced={mustChangePassword} />
          </SetupStep>

          {/* Step 2 — recovery questions */}
          <SetupStep
            num={2}
            title="Set up password recovery questions"
            status={mustChangePassword ? "locked" : mustSetupRecovery ? "active" : "done"}
          >
            <RecoveryCard mandatory />
          </SetupStep>
        </div>
      ) : (
        /* ── Normal account management (all steps done) ─────────────────── */
        <div className="grid g2" style={{ alignItems: "start" }}>
          <div className="card" style={{ maxWidth: 440 }}>
            <h3 style={{ marginTop: 0 }}>Change password</h3>
            <PasswordCard forced={false} />
          </div>
          <div className="card" style={{ maxWidth: 520 }}>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}><ShieldCheck size={17} style={{ verticalAlign: -3 }} /> Password recovery questions</h3>
              <Badge kind="good">Set up</Badge>
            </div>
            <RecoveryCard mandatory={false} />
          </div>
          {isOwner && <GmailRecoveryCard />}
        </div>
      )}
    </>
  );
}
