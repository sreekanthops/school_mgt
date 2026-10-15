import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Async, Badge, PageHead, useLoad } from "../components/ui.jsx";

/** Change password. Also used on its own when an admin issued a temporary password (forced = true). */
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
    <div className="card" style={{ maxWidth: 440 }}>
      <h3 style={{ marginTop: 0 }}>{forced ? "Choose your own password" : "Change password"}</h3>
      {forced && <p className="muted">You signed in with a temporary password from the school. Enter it below as the current password, then choose a new one to continue.</p>}
      {msg && <div className={msg.bad ? "error" : "notice"}>{msg.text}</div>}
      <form onSubmit={submit} className="grid" style={{ gap: 12 }}>
        <div className="field"><label htmlFor="cp">{forced ? "Temporary password" : "Current password"}</label>
          <input id="cp" type="password" autoComplete="current-password" required value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} /></div>
        <div className="field"><label htmlFor="np">New password (min 10 characters)</label>
          <input id="np" type="password" autoComplete="new-password" required minLength={10} maxLength={128} value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} /></div>
        <div className="field"><label htmlFor="cf">Confirm new password</label>
          <input id="cf" type="password" autoComplete="new-password" required value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></div>
        <button className="btn" disabled={busy}>{busy ? "Saving…" : "Update password"}</button>
      </form>
    </div>
  );
}

/** Pick 3 random questions and answer them, so the password can be reset later without staff help. */
function RecoveryCard() {
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
      await api("/auth/recovery/setup", { method: "POST", body: { current_password: pw, answers: qs.map((q, i) => ({ id: q.id, answer: answers[i] })) } });
      setMsg({ text: "Saved. Remember these answers, you will be asked the same three questions if you forget your password." });
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
        <div className="card" style={{ maxWidth: 520 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}><ShieldCheck size={17} style={{ verticalAlign: -3 }} /> Password recovery questions</h3>
            {d.configured ? <Badge kind="good">Set up</Badge> : <Badge kind="warn">Not set up</Badge>}
          </div>
          <p className="muted">
            {d.configured ? "Want different questions or answers? Answer a new set below to replace the old one."
              : "Answer these three questions now. If you ever forget your password, you can reset it yourself by answering them again."}
          </p>
          {msg && <div className={msg.bad ? "error" : "notice"}>{msg.text}</div>}
          <form onSubmit={(e) => save(e, d.questions)} className="grid" style={{ gap: 12 }}>
            {d.questions.map((q, i) => (
              <div className="field" key={q.id}>
                <label htmlFor={`rq${i}`}>{i + 1}. {q.text}</label>
                <input id={`rq${i}`} value={answers[i]} maxLength={80} required autoComplete="off"
                  onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))} />
              </div>
            ))}
            <div className="field"><label htmlFor="rpw">Your current password (to confirm it's you)</label>
              <input id="rpw" type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></div>
            <div className="row">
              <button className="btn" disabled={busy}>{busy ? "Saving…" : d.configured ? "Replace questions" : "Save answers"}</button>
              <button type="button" className="btn ghost" onClick={() => { setAnswers(["", "", ""]); setTick((t) => t + 1); }}>Show different questions</button>
            </div>
            <p className="small muted" style={{ margin: 0 }}>Answers are stored scrambled (hashed) and cannot be read by anyone, including admins. Capital letters and punctuation don't matter.</p>
          </form>
        </div>
      )}
    </Async>
  );
}

export default function Account() {
  const { session } = useAuth();
  const forced = !!session.must_change;
  return (
    <>
      <PageHead title="My Account" sub={`${session.name} · ${session.username} · ${session.role}`} />
      {forced && <div className="error" role="alert">Your password was set by the school admin. Choose your own to continue.</div>}
      <div className="grid g2" style={{ alignItems: "start" }}>
        <PasswordCard forced={forced} />
        {!forced && <RecoveryCard />}
      </div>
    </>
  );
}
