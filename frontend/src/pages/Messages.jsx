import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, Eraser, MessageSquarePlus, Search, Send } from "lucide-react";
import { api } from "../api.js";
import { Confirm, Empty, Modal, PageHead, Photo } from "../components/ui.jsx";

const when = (iso) => {
  const d = new Date(iso);
  const same = d.toDateString() === new Date().toDateString();
  return same ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : d.toLocaleDateString([], { day: "numeric", month: "short" });
};
const Av = ({ c, size = 40 }) => (
  <Photo kind={c.photo?.kind} id={c.photo?.id} name={c.name} has={!!c.photo?.has} v={c.photo?.v} size={size} />
);

function NewChat({ onPick, onClose }) {
  const [list, setList] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api("/messages/contacts").then(setList).catch(() => setList([])); }, []);
  const shown = (list ?? []).filter((c) => c.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <Modal title="New message" onClose={onClose}>
      <div className="search" style={{ marginBottom: 10 }}><Search size={16} /><input autoFocus placeholder="Search people" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%" }} /></div>
      <div style={{ maxHeight: 360, overflowY: "auto" }}>
        {list === null && <Empty>Loading…</Empty>}
        {list && shown.length === 0 && <Empty>No one to message.</Empty>}
        {shown.map((c) => (
          <button key={c.id} className="mail-item" onClick={() => onPick(c)}>
            <Av c={c} /><div className="meta"><b>{c.name}</b><span>{c.subtitle}</span></div>
          </button>
        ))}
      </div>
    </Modal>
  );
}

export default function Messages() {
  const [params, setParams] = useSearchParams();
  const [threads, setThreads] = useState(null);
  const [active, setActive] = useState(null); // contact object
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [picking, setPicking] = useState(false);
  const [clearing, setClearing] = useState(false);
  const end = useRef(null);

  const loadThreads = () => api("/messages/threads").then(setThreads).catch((e) => setErr(e.message));
  const openChat = async (c) => {
    setErr("");
    setActive(c);
    try {
      const r = await api(`/messages/with/${c.id}`);
      setActive(r.with);
      setMsgs(r.messages);
      loadThreads();
    } catch (e) {
      setErr(e.message);
      setMsgs([]);
    }
  };

  useEffect(() => { loadThreads(); }, []);
  // deep link from the assistant: /messages?to=<userId>
  useEffect(() => {
    const to = Number(params.get("to"));
    if (to) {
      openChat({ id: to, name: "…", subtitle: "" });
      setParams({}, { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // light polling so new messages appear without a refresh
  useEffect(() => {
    const t = setInterval(() => {
      loadThreads();
      if (active?.id) api(`/messages/with/${active.id}`).then((r) => setMsgs(r.messages)).catch(() => {});
    }, 8000);
    return () => clearInterval(t);
  }, [active?.id]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, active?.id]);

  async function send(e) {
    e.preventDefault();
    const body = text.trim();
    if (!body || !active) return;
    setText("");
    try {
      const m = await api(`/messages/with/${active.id}`, { method: "POST", body: { body } });
      setMsgs((x) => [...x, m]);
      loadThreads();
    } catch (x) {
      setErr(x.message);
      setText(body);
    }
  }

  async function clear() {
    await api(`/messages/with/${active.id}`, { method: "DELETE" });
    setMsgs([]);
    loadThreads();
  }

  return (
    <>
      <PageHead title="Messages" sub="Private chats with people in your school. Chats stay until you clear them.">
        <button className="btn" onClick={() => setPicking(true)}><MessageSquarePlus size={16} /> New message</button>
      </PageHead>
      {err && <div className="error">{err}</div>}
      <div className={`card mail ${active ? "open" : ""}`}>
        <div className="mail-list">
          <div className="scroll">
            {threads === null && <Empty>Loading…</Empty>}
            {threads?.length === 0 && <Empty>No conversations yet. Start one with “New message”.</Empty>}
            {threads?.map((t) => (
              <button key={t.id} className={`mail-item ${active?.id === t.id ? "on" : ""}`} onClick={() => openChat(t)}>
                <Av c={t} />
                <div className="meta"><b>{t.name}</b><span>{t.last_mine ? "You: " : ""}{t.last}</span></div>
                <div style={{ textAlign: "right" }}>
                  <div className="small muted">{when(t.last_at)}</div>
                  {t.unread > 0 && <span className="unread-dot">{t.unread}</span>}
                </div>
              </button>
            ))}
          </div>
        </div>
        <div className="mail-pane">
          {!active ? (
            <Empty>Select a conversation or start a new one.</Empty>
          ) : (
            <>
              <div className="mail-head">
                <button className="icon-btn mail-back" onClick={() => setActive(null)} aria-label="Back"><ArrowLeft size={18} /></button>
                <Av c={active} size={38} />
                <div style={{ flex: 1 }}><b>{active.name}</b><div className="small muted">{active.subtitle}</div></div>
                <button className="btn ghost sm" onClick={() => setClearing(true)} disabled={msgs.length === 0}><Eraser size={14} /> Clear chat</button>
              </div>
              <div className="mail-msgs">
                {msgs.length === 0 && <Empty>No messages yet. Say hello.</Empty>}
                {msgs.map((m) => (
                  <div key={m.id} className={`dm ${m.mine ? "mine" : "them"}`}>{m.body}<span className="ts">{when(m.at)}</span></div>
                ))}
                <div ref={end} />
              </div>
              <form className="mail-send" onSubmit={send}>
                <input value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Type a message…" aria-label="Message" />
                <button className="btn" disabled={!text.trim()}><Send size={16} /> Send</button>
              </form>
            </>
          )}
        </div>
      </div>
      {picking && <NewChat onClose={() => setPicking(false)} onPick={(c) => { setPicking(false); openChat(c); }} />}
      {clearing && (
        <Confirm title="Clear this chat?" message={`Remove your conversation with ${active.name}? They keep their own copy.`}
          onClose={() => setClearing(false)} onConfirm={clear} />
      )}
    </>
  );
}
