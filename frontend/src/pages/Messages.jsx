import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ChevronRight, Eraser, ExternalLink, MessageSquarePlus, Search, Send, Users } from "lucide-react";
import { api, GRADES } from "../api.js";
import { Confirm, Empty, Modal, PageHead, Photo } from "../components/ui.jsx";

const when = (iso) => {
  const d = new Date(iso);
  const same = d.toDateString() === new Date().toDateString();
  return same
    ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString([], { day: "numeric", month: "short" });
};

const Av = ({ c, size = 40 }) => (
  <Photo kind={c.photo?.kind} id={c.photo?.id} name={c.name} has={!!c.photo?.has} v={c.photo?.v} size={size} />
);

/** Returns the URL to jump to a person's full profile page. */
function profileUrl(c) {
  if (c.staff_id)   return `/staff/${c.staff_id}`;
  if (c.student_id) return `/students/${c.student_id}`;
  return null;
}

// ── one-line identity string shown under the name ────────────────────────────
function identityLine(c) {
  if (c.role === "student" && c.grade) {
    const cls = c.grade === "LKG" || c.grade === "UKG" ? c.grade : `Class ${c.grade}`;
    return `${cls}-${c.section}${c.admission_no ? ` · ${c.admission_no}` : ""}`;
  }
  if (c.designation) return c.designation;
  if (c.role === "admin") return "School owner / Admin";
  return c.subtitle || c.role;
}

// ── New-message contact picker ────────────────────────────────────────────────

function NewChat({ onPick, onClose }) {
  const [list, setList] = useState(null);
  const [q, setQ] = useState("");
  const [activeGroup, setActiveGroup] = useState("staff"); // "staff" | grade string

  useEffect(() => {
    api("/messages/contacts").then(setList).catch(() => setList([]));
  }, []);

  if (list === null) {
    return (
      <Modal title="New message" onClose={onClose}>
        <Empty>Loading contacts…</Empty>
      </Modal>
    );
  }

  const staff    = list.filter((c) => c.role !== "student");
  const students = list.filter((c) => c.role === "student");

  // Derive available grades in canonical order
  const availGrades = GRADES.filter((g) => students.some((c) => c.grade === g));

  // Apply search query
  const qLow = q.toLowerCase();
  const filterContacts = (arr) =>
    q ? arr.filter((c) =>
      c.name.toLowerCase().includes(qLow) ||
      (c.subtitle || "").toLowerCase().includes(qLow) ||
      (c.admission_no || "").toLowerCase().includes(qLow) ||
      (c.employee_id || "").toLowerCase().includes(qLow)
    ) : arr;

  // Decide what to show
  let shown = [];
  let isSearching = q.length > 0;
  if (isSearching) {
    shown = filterContacts(list);
  } else if (activeGroup === "staff") {
    shown = staff;
  } else {
    // Filter by selected grade; group by section
    shown = students.filter((c) => c.grade === activeGroup);
  }

  // Section sub-groups (only used when showing a grade)
  const sections = activeGroup !== "staff" && !isSearching
    ? [...new Set(shown.map((c) => c.section).filter(Boolean))].sort()
    : [];

  return (
    <Modal title="New message" onClose={onClose} wide>
      {/* Search bar */}
      <div className="search" style={{ marginBottom: 12 }}>
        <Search size={16} />
        <input autoFocus placeholder="Search by name, class, ID…" value={q}
          onChange={(e) => setQ(e.target.value)} style={{ width: "100%" }} />
      </div>

      {!isSearching && (
        /* Group tabs: Staff | Class 1 | Class 2 … */
        <div className="tabs" style={{ marginBottom: 12, flexWrap: "wrap" }}>
          <button className={activeGroup === "staff" ? "on" : ""}
            onClick={() => setActiveGroup("staff")}>
            <Users size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
            Staff &amp; Admins ({staff.length})
          </button>
          {availGrades.map((g) => {
            const cnt = students.filter((c) => c.grade === g).length;
            const label = g === "LKG" || g === "UKG" ? g : `Class ${g}`;
            return (
              <button key={g} className={activeGroup === g ? "on" : ""}
                onClick={() => setActiveGroup(g)}>
                {label} ({cnt})
              </button>
            );
          })}
        </div>
      )}

      <div style={{ maxHeight: 400, overflowY: "auto" }}>
        {shown.length === 0 && (
          <Empty>{isSearching ? "No one matches that search." : "No one in this group."}</Empty>
        )}

        {isSearching || activeGroup === "staff" ? (
          /* Flat list */
          shown.map((c) => (
            <button key={c.id} className="mail-item" onClick={() => onPick(c)}>
              <Av c={c} />
              <div className="meta">
                <b>{c.name}</b>
                <span>{identityLine(c)}</span>
              </div>
              <ChevronRight size={15} style={{ color: "var(--muted)", flexShrink: 0 }} />
            </button>
          ))
        ) : (
          /* Grouped by section */
          sections.length > 0 ? sections.map((sec) => {
            const inSec = shown.filter((c) => c.section === sec);
            return (
              <div key={sec}>
                <div style={{
                  fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em",
                  color: "var(--muted)", padding: "8px 12px 4px", background: "var(--surface, #f7f8fa)",
                }}>
                  Section {sec}
                </div>
                {inSec.map((c) => (
                  <button key={c.id} className="mail-item" onClick={() => onPick(c)}>
                    <Av c={c} />
                    <div className="meta">
                      <b>{c.name}</b>
                      <span>{c.admission_no || identityLine(c)}</span>
                    </div>
                    <ChevronRight size={15} style={{ color: "var(--muted)", flexShrink: 0 }} />
                  </button>
                ))}
              </div>
            );
          }) : (
            /* No sections — flat list under grade */
            shown.map((c) => (
              <button key={c.id} className="mail-item" onClick={() => onPick(c)}>
                <Av c={c} />
                <div className="meta">
                  <b>{c.name}</b>
                  <span>{c.admission_no || identityLine(c)}</span>
                </div>
                <ChevronRight size={15} style={{ color: "var(--muted)", flexShrink: 0 }} />
              </button>
            ))
          )
        )}
      </div>
    </Modal>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

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

  const loadThreads = () =>
    api("/messages/threads").then(setThreads).catch((e) => setErr(e.message));

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

  // deep link: /messages?to=<userId>
  useEffect(() => {
    const to = Number(params.get("to"));
    if (to) {
      openChat({ id: to, name: "…", subtitle: "" });
      setParams({}, { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // light polling
  useEffect(() => {
    const t = setInterval(() => {
      loadThreads();
      if (active?.id) {
        api(`/messages/with/${active.id}`).then((r) => setMsgs(r.messages)).catch(() => {});
      }
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

  const activeProfile = active ? profileUrl(active) : null;

  return (
    <>
      <PageHead title="Messages" sub="Private chats with people in your school. Chats stay until you clear them.">
        <button className="btn" onClick={() => setPicking(true)}>
          <MessageSquarePlus size={16} /> New message
        </button>
      </PageHead>

      {err && <div className="error">{err}</div>}

      <div className={`card mail ${active ? "open" : ""}`}>
        {/* ── Thread list ─────────────────────────────────────────────── */}
        <div className="mail-list">
          <div className="scroll">
            {threads === null && <Empty>Loading…</Empty>}
            {threads?.length === 0 && (
              <Empty>No conversations yet. Start one with "New message".</Empty>
            )}
            {threads?.map((t) => (
              <button key={t.id}
                className={`mail-item ${active?.id === t.id ? "on" : ""}`}
                onClick={() => openChat(t)}>
                <Av c={t} />
                <div className="meta">
                  <b>{t.name}</b>
                  {/* Show identity subtitle under name in thread list */}
                  <span style={{ fontSize: 11, opacity: 0.75 }}>{identityLine(t)}</span>
                  <span>{t.last_mine ? "You: " : ""}{t.last}</span>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0 }}>
                  <div className="small muted">{when(t.last_at)}</div>
                  {t.unread > 0 && <span className="unread-dot">{t.unread}</span>}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* ── Chat pane ───────────────────────────────────────────────── */}
        <div className="mail-pane">
          {!active ? (
            <Empty>Select a conversation or start a new one.</Empty>
          ) : (
            <>
              <div className="mail-head">
                <button className="icon-btn mail-back" onClick={() => setActive(null)} aria-label="Back">
                  <ArrowLeft size={18} />
                </button>
                <Av c={active} size={38} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row" style={{ gap: 6, alignItems: "center" }}>
                    <b style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {active.name}
                    </b>
                    {/* Clickable link to their full profile */}
                    {activeProfile && (
                      <Link to={activeProfile} title="View full profile"
                        style={{ color: "var(--primary)", opacity: 0.8, flexShrink: 0 }}>
                        <ExternalLink size={13} />
                      </Link>
                    )}
                  </div>
                  {/* Identity line: Class 9-A · ADM2024 for students, Designation for staff */}
                  <div className="small muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {identityLine(active)}
                  </div>
                </div>
                <button className="btn ghost sm" onClick={() => setClearing(true)} disabled={msgs.length === 0}>
                  <Eraser size={14} /> Clear chat
                </button>
              </div>

              <div className="mail-msgs">
                {msgs.length === 0 && <Empty>No messages yet. Say hello.</Empty>}
                {msgs.map((m) => (
                  <div key={m.id} className={`dm ${m.mine ? "mine" : "them"}`}>
                    {m.body}
                    <span className="ts">{when(m.at)}</span>
                  </div>
                ))}
                <div ref={end} />
              </div>

              <form className="mail-send" onSubmit={send}>
                <input value={text} maxLength={1000}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Type a message…" aria-label="Message" />
                <button className="btn" disabled={!text.trim()}><Send size={16} /> Send</button>
              </form>
            </>
          )}
        </div>
      </div>

      {picking && (
        <NewChat
          onClose={() => setPicking(false)}
          onPick={(c) => { setPicking(false); openChat(c); }}
        />
      )}
      {clearing && (
        <Confirm
          title="Clear this chat?"
          message={`Remove your conversation with ${active.name}? They keep their own copy.`}
          onClose={() => setClearing(false)}
          onConfirm={clear}
        />
      )}
    </>
  );
}
