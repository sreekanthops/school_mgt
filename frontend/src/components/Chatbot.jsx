import { useEffect, useRef, useState } from "react";
import { MessageCircle, Send, Sparkles, X } from "lucide-react";
import { api } from "../api.js";

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [sugg, setSugg] = useState([]);
  const [msgs, setMsgs] = useState([{ who: "bot", text: "Hi! Ask me about students, marks, staff, subjects, chapters, events or goals." }]);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, open]);
  useEffect(() => {
    if (open && sugg.length === 0) {
      api("/chat", { method: "POST", body: { question: "help" } }).then((r) => setSugg(r.suggestions)).catch(() => {});
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(text) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { who: "me", text: q }]);
    setBusy(true);
    try {
      const r = await api("/chat", { method: "POST", body: { question: q } });
      setMsgs((m) => [...m, { who: "bot", text: r.answer }]);
      setSugg(r.suggestions);
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
          <div className="chat-head">
            <span className="row" style={{ gap: 8 }}><Sparkles size={18} /> School Assistant</span>
            <button className="icon-btn" style={{ color: "#fff" }} onClick={() => setOpen(false)} aria-label="Close"><X size={18} /></button>
          </div>
          <div className="chat-body">
            {msgs.map((m, i) => <div key={i} className={`msg ${m.who}`}>{m.text}</div>)}
            {msgs.length === 1 && <div className="sugg">{sugg.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>}
            {busy && <div className="msg bot muted">Thinking…</div>}
            <div ref={end} />
          </div>
          <form className="chat-foot" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} maxLength={500} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about the school…" />
            <button className="btn" disabled={busy} aria-label="Send"><Send size={16} /></button>
          </form>
        </div>
      )}
      <button className="fab" aria-label="Open assistant" onClick={() => setOpen((o) => !o)}>{open ? <X size={24} /> : <MessageCircle size={26} />}</button>
    </>
  );
}
