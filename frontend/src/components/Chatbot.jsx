import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Bot, MessageCircle, Send, Sparkles, Trash2, X } from "lucide-react";
import { api } from "../api.js";
import { Confirm } from "./ui.jsx";

const WELCOME = "Hi! I'm your school assistant. Ask me about students, marks, fees, staff, subjects, chapters, events or goals.";
const time = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "");

/** Only ever navigate to in-app paths, never to anything the server could point elsewhere. */
const safePath = (p) => typeof p === "string" && p.startsWith("/") && !p.startsWith("//");

function Rich({ m, go }) {
  const [head, ...rest] = (m.text || "").split("\n");
  return (
    <>
      <div className="bubble-text"><b>{head}</b>{rest.length > 0 && <>{"\n"}{rest.join("\n")}</>}</div>
      {m.stats?.length > 0 && (
        <div className="cstats">
          {m.stats.map((s, i) => (
            <div key={i} className={`cstat ${s.tone || ""}`}><span>{s.label}</span><b>{s.value}</b></div>
          ))}
        </div>
      )}
      {m.bars?.length > 0 && (
        <div className="cbars">
          {m.bars.map((b, i) => (
            <div key={i} className="cbar">
              <div className="cbar-top"><span title={b.label}>{b.label}</span><b>{b.pct}%</b></div>
              <div className={`bar ${b.tone}`}><i style={{ width: `${Math.max(0, Math.min(100, b.pct))}%` }} /></div>
            </div>
          ))}
        </div>
      )}
      {m.actions?.length > 0 && (
        <div className="cactions">
          {m.actions.filter((a) => safePath(a.to)).map((a, i) => (
            <button key={i} className="cbtn" onClick={() => go(a.to)}>{a.label}<ArrowUpRight size={13} /></button>
          ))}
        </div>
      )}
    </>
  );
}

export default function Chatbot() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [sugg, setSugg] = useState([]);
  const [msgs, setMsgs] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const end = useRef(null);

  useEffect(() => {
    if (!open || loaded) return;
    api("/chat/history")
      .then((r) => { setMsgs(r.messages); setSugg(r.suggestions); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, [open, loaded]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, open, busy]);

  const go = (to) => { setOpen(false); nav(to); };

  async function send(text) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { id: `t${Date.now()}`, who: "me", text: q, at: new Date().toISOString() }]);
    setBusy(true);
    try {
      const r = await api("/chat", { method: "POST", body: { question: q } });
      setMsgs((m) => [...m, { id: `b${Date.now()}`, who: "bot", text: r.answer, stats: r.stats, bars: r.bars, actions: r.actions, at: new Date().toISOString() }]);
      setSugg(r.suggestions);
    } catch (e) {
      setMsgs((m) => [...m, { id: `e${Date.now()}`, who: "bot", text: `Sorry, that did not work. ${e.message}`, at: new Date().toISOString() }]);
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    await api("/chat/history", { method: "DELETE" });
    setMsgs([]);
  }

  return (
    <>
      {open && (
        <div className="chat" role="dialog" aria-label="School assistant">
          <div className="chat-head">
            <span className="chat-bot"><Sparkles size={18} /></span>
            <div className="chat-title"><b>School Assistant</b><small><i className="dot" /> Answers from your school's live data</small></div>
            <button className="chat-ic" onClick={() => setConfirmClear(true)} disabled={msgs.length === 0} aria-label="Clear chat" title="Clear chat"><Trash2 size={16} /></button>
            <button className="chat-ic" onClick={() => setOpen(false)} aria-label="Close"><X size={18} /></button>
          </div>
          <div className="chat-body">
            <div className="row-bot"><span className="av"><Bot size={15} /></span><div className="msg bot"><div className="bubble-text">{WELCOME}</div></div></div>
            {msgs.map((m) => (
              m.who === "me" ? (
                <div key={m.id} className="row-me"><div className="msg me">{m.text}<span className="ts">{time(m.at)}</span></div></div>
              ) : (
                <div key={m.id} className="row-bot"><span className="av"><Bot size={15} /></span>
                  <div className="msg bot"><Rich m={m} go={go} /><span className="ts">{time(m.at)}</span></div></div>
              )
            ))}
            {busy && <div className="row-bot"><span className="av"><Bot size={15} /></span><div className="msg bot typing"><i /><i /><i /></div></div>}
            <div ref={end} />
          </div>
          {sugg.length > 0 && (
            <div className="sugg-row" aria-label="Suggestions">
              {sugg.map((s) => <button key={s} onClick={() => send(s)} disabled={busy}>{s}</button>)}
            </div>
          )}
          <form className="chat-foot" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} maxLength={500} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about the school…" aria-label="Message" />
            <button className="send" disabled={busy || !input.trim()} aria-label="Send"><Send size={16} /></button>
          </form>
          {confirmClear && (
            <Confirm title="Clear this chat?" message="Your conversation with the assistant will be deleted. This only affects your own chat."
              onClose={() => setConfirmClear(false)} onConfirm={clear} />
          )}
        </div>
      )}
      <button className="fab" aria-label="Open assistant" onClick={() => setOpen((o) => !o)}>{open ? <X size={24} /> : <MessageCircle size={26} />}</button>
    </>
  );
}
