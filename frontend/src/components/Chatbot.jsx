import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const START = [
  "How many students are in class 5?", "Which students have pending fees?", "Who are the top performers?",
  "Which subjects does class 8 have?", "Who is the class teacher of class 3?", "What events are coming up?",
];

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([{ who: "bot", text: "Hi! Ask me about students, marks, fees, staff, subjects, events or goals." }]);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, open]);

  async function send(text) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { who: "me", text: q }]);
    setBusy(true);
    try {
      const r = await api("/chat", { method: "POST", body: { question: q } });
      setMsgs((m) => [...m, { who: "bot", text: r.answer }]);
    } catch (e) {
      setMsgs((m) => [...m, { who: "bot", text: `Sorry: ${e.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {open && (
        <div className="chat" role="dialog" aria-label="School assistant">
          <div className="chat-head"><span>School Assistant</span><span style={{ cursor: "pointer" }} onClick={() => setOpen(false)}>✕</span></div>
          <div className="chat-body">
            {msgs.map((m, i) => <div key={i} className={`msg ${m.who}`}>{m.text}</div>)}
            {msgs.length === 1 && (
              <div className="sugg">{START.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
            )}
            {busy && <div className="msg bot muted">Thinking…</div>}
            <div ref={end} />
          </div>
          <form className="chat-foot" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} maxLength={500} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about the school…" />
            <button className="btn" disabled={busy}>Send</button>
          </form>
        </div>
      )}
      <button className="fab" aria-label="Open assistant" onClick={() => setOpen((o) => !o)}>{open ? "✕" : "💬"}</button>
    </>
  );
}
