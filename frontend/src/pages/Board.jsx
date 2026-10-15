import { useEffect, useRef, useState } from "react";
import { Check, Flame, Lightbulb, Send, ShieldCheck, ThumbsDown, ThumbsUp, Trash2, TrendingUp } from "lucide-react";
import { api } from "../api.js";
import { Async, Confirm, Empty, PageHead, useLoad } from "../components/ui.jsx";

const SORTS = [["new", "Newest", Lightbulb], ["top", "Most agreed", TrendingUp], ["debated", "Most debated", Flame]];
const MAX = 300;

function ago(iso) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.round(m / 60)} h ago`;
  return `${Math.round(m / 1440)} d ago`;
}

function Composer({ onPosted }) {
  const [text, setText] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef(0);

  // live preview: the server decides, this only shows the warning before you press Post
  useEffect(() => {
    clearTimeout(timer.current);
    if (text.trim().length < 3) { setBlocked(false); return undefined; }
    timer.current = setTimeout(() => {
      api("/board/check", { method: "POST", body: { text } }).then((r) => setBlocked(!r.ok)).catch(() => {});
    }, 350);
    return () => clearTimeout(timer.current);
  }, [text]);

  async function post(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const note = await api("/board", { method: "POST", body: { text } });
      setText("");
      setBlocked(false);
      onPosted(note);
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card board-composer" onSubmit={post}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Share an idea or opinion</h2>
        <span className="badge good"><ShieldCheck size={12} /> Anonymous</span>
      </div>
      <p className="small muted" style={{ margin: "4px 0 10px" }}>
        Nobody can see who wrote a note, not even the school staff. Keep it kind and about school life. Rude, sexual or
        threatening wording, phone numbers, e-mail addresses and links are blocked.
      </p>
      {err && <div className="error">{err}</div>}
      <textarea className={`board-input ${blocked ? "blocked" : ""}`} rows={3} maxLength={MAX} value={text} aria-label="Your idea or opinion"
        placeholder="e.g. Can we have a longer lunch break on Fridays?" onChange={(e) => setText(e.target.value)} />
      <div className="row" style={{ justifyContent: "space-between", marginTop: 8 }}>
        <span className={`small ${blocked ? "board-warn" : "muted"}`} role={blocked ? "alert" : undefined}>
          {blocked ? "This contains words or details that are not allowed. Please rephrase." : `${text.length} / ${MAX}`}
        </span>
        <button className="btn" disabled={busy || blocked || text.trim().length < 3}><Send size={15} /> {busy ? "Posting…" : "Post anonymously"}</button>
      </div>
    </form>
  );
}

function Note({ n, canVote, onChange, onReload, onDelete }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function vote(value) {
    setBusy(true);
    setErr("");
    try {
      if (n.my_vote === value) {
        await api(`/board/${n.id}/vote`, { method: "DELETE" });
        onReload();
      } else {
        onChange(await api(`/board/${n.id}/vote`, { method: "POST", body: { value } }));
      }
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  const voted = n.votes > 0;
  return (
    <article className={`note ${n.color}`} style={{ "--tilt": `${n.tilt}deg` }}>
      <span className="pin" aria-hidden="true" />
      {n.can_delete && (
        <button className="note-del" aria-label="Delete this note" title={n.mine ? "Delete your note" : "Remove (moderator)"} onClick={() => onDelete(n)}>
          <Trash2 size={14} />
        </button>
      )}
      <p className="note-text">{n.text}</p>
      <div className="note-meta">
        {n.mine && <span>your note · </span>}{ago(n.created_at)}
      </div>
      {voted ? (
        <div className="note-bars" aria-label={`${n.agree_pct}% agree, ${n.disagree_pct}% disagree, ${n.votes} votes`}>
          <div className="split"><i className="yes" style={{ width: `${n.agree_pct}%` }} /><i className="no" style={{ width: `${n.disagree_pct}%` }} /></div>
          <div className="split-legend"><span>{n.agree_pct}% agree</span><span>{n.disagree_pct}% disagree</span></div>
          <div className="note-meta">{n.votes} vote{n.votes === 1 ? "" : "s"} · {n.participation_pct}% of students</div>
        </div>
      ) : <div className="note-meta">No votes yet</div>}
      {canVote && !n.mine && (
        <div className="note-vote">
          <button className={n.my_vote === "agree" ? "on yes" : ""} disabled={busy} onClick={() => vote("agree")} aria-pressed={n.my_vote === "agree"}>
            <ThumbsUp size={14} /> Agree {n.my_vote === "agree" && <Check size={12} />}
          </button>
          <button className={n.my_vote === "disagree" ? "on no" : ""} disabled={busy} onClick={() => vote("disagree")} aria-pressed={n.my_vote === "disagree"}>
            <ThumbsDown size={14} /> Disagree {n.my_vote === "disagree" && <Check size={12} />}
          </button>
        </div>
      )}
      {err && <div className="small board-warn">{err}</div>}
    </article>
  );
}

export default function Board() {
  const [sort, setSort] = useState("new");
  const [tick, setTick] = useState(0);
  const [items, setItems] = useState(null);
  const [del, setDel] = useState(null);
  const state = useLoad(async () => {
    const r = await api(`/board?sort=${sort}`);
    setItems(r.items);
    return r;
  }, [sort, tick]);
  const reload = () => setTick((t) => t + 1);
  const replace = (note) => setItems((list) => list.map((x) => (x.id === note.id ? note : x)));

  return (
    <>
      <PageHead title="Idea Board" sub="Anonymous ideas and opinions about school life. Students can agree or disagree, once each." />
      <Async state={state}>
        {(d) => (
          <>
            <Composer onPosted={reload} />
            <div className="tabs" style={{ margin: "18px 0 8px" }}>
              {SORTS.map(([k, l, Icon]) => <button key={k} className={sort === k ? "on" : ""} onClick={() => setSort(k)}><Icon size={13} style={{ verticalAlign: -2 }} /> {l}</button>)}
            </div>
            {!d.can_vote && <p className="small muted">Only students can vote. You can read, post and {d.can_moderate ? "remove inappropriate notes" : "delete your own notes"}.</p>}
            {(items ?? d.items).length === 0 ? <Empty>No notes yet. Be the first to share an idea.</Empty> : (
              <div className="board">
                {(items ?? d.items).map((n) => (
                  <Note key={n.id} n={n} canVote={d.can_vote} onChange={replace} onReload={reload} onDelete={setDel} />
                ))}
              </div>
            )}
          </>
        )}
      </Async>
      {del && (
        <Confirm title="Delete note" message={del.mine ? "Delete your note? Its votes are removed too." : "Remove this note from the board? Its votes are removed too."}
          onClose={() => setDel(null)} onConfirm={async () => { await api(`/board/${del.id}`, { method: "DELETE" }); reload(); }} />
      )}
    </>
  );
}
