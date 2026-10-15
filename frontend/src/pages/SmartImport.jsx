import { useState } from "react";
import { AlertTriangle, CheckCircle2, FileUp, RotateCcw, Sparkles, Upload } from "lucide-react";
import { ApiError, api, getSession } from "../api.js";
import { Async, Badge, Confirm, PageHead, useLoad } from "../components/ui.jsx";

const EXAMS = ["UT1", "Midterm", "UT2", "Final"];
const MODES = ["Cash", "UPI", "Card", "Cheque", "Bank Transfer"];
const when = (iso) => new Date(iso).toLocaleString();

async function upload(file) {
  const res = await fetch(`/api/import/upload?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", Authorization: `Bearer ${getSession()?.token}` },
    body: file,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new ApiError(res.status, typeof data?.detail === "string" ? data.detail : "The file could not be read");
  return data;
}

// names are user-entered: a leading = + - @ would run as a formula in a spreadsheet, so it is defused (passwords are server-generated and kept exact)
const cell = (v) => `"${(/^[=+\-@\t\r]/.test(v) ? "'" + v : String(v)).replace(/"/g, '""')}"`;
const csvOf = (logins) =>
  ["Login ID,Name,Role,Class,Temporary password", ...logins.map((l) => [l.login, cell(l.name), cell(l.role), l.class, l.temp_password].join(","))].join("\n");

function saveCsv(logins) {
  const url = URL.createObjectURL(new Blob(["\ufeff" + csvOf(logins)], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "new-logins.csv" });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const initial = (up) => up.sheets.map((s) => ({
  index: s.index, include: !!s.kind, kind: s.kind || "students", header_row: s.header_row, mapping: { ...s.mapping },
  on_duplicate: "skip", year: "", exam: "", mode: "Cash",
}));
const payload = (cfg, opts) => ({
  sheets: cfg.map((c) => ({ index: c.index, include: c.include, kind: c.kind, header_row: c.header_row, mapping: c.mapping,
    on_duplicate: c.on_duplicate, year: c.year || null, exam: c.exam || null, mode: c.mode })),
  create_logins: opts.logins, create_subjects: opts.subjects,
});

function Counts({ r }) {
  return (
    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
      {r.new > 0 && <Badge kind="good">{r.new} new</Badge>}
      {r.matched > 0 && <Badge>{r.matched} already there</Badge>}
      {r.updated > 0 && <Badge kind="warn">{r.updated} updated</Badge>}
      {r.skipped > 0 && <Badge>{r.skipped} skipped</Badge>}
      {r.error_count > 0 && <Badge kind="bad">{r.error_count} to fix</Badge>}
    </div>
  );
}

function SheetCard({ s, up, cfg, set }) {
  const kind = up.kinds[cfg.kind];
  const heads = s.headers.map((h, i) => ({ h: h || `(column ${i + 1})`, i }));
  const used = new Set(Object.values(cfg.mapping));
  const setMap = (field, v) => {
    const m = { ...cfg.mapping };
    if (v === "") delete m[field]; else m[field] = Number(v);
    set({ mapping: m });
  };
  return (
    <div className="card" style={{ opacity: cfg.include ? 1 : 0.55 }}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div>
          <b>{s.name}</b> <span className="muted small">· {s.rows} rows</span>
          {s.suggested_by === "ai" && <span className="small" style={{ marginLeft: 8 }}><Sparkles size={12} style={{ verticalAlign: -1 }} /> matched by AI from the headings</span>}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <select aria-label="What this sheet contains" value={cfg.kind} onChange={(e) => set({ kind: e.target.value, mapping: {}, include: true })} style={{ width: "auto" }}>
            {Object.entries(up.kinds).map(([k, v]) => <option key={k} value={k} disabled={!v.allowed}>{v.label}{v.allowed ? "" : " (no permission)"}</option>)}
          </select>
          <label className="row small" style={{ gap: 6 }}>
            <input type="checkbox" style={{ width: "auto" }} checked={cfg.include} onChange={(e) => set({ include: e.target.checked })} /> Import
          </label>
        </div>
      </div>
      {!s.kind && cfg.include && <p className="small muted" style={{ marginTop: 8 }}>We could not tell what this sheet holds. Choose its type above, then match the columns.</p>}
      {cfg.include && kind && (
        <>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(230px,1fr))", gap: 10, marginTop: 12 }}>
            {kind.fields.map((f) => (
              <div className="field" key={f.key}>
                <label>{f.label}{f.required ? " *" : ""}</label>
                <select value={cfg.mapping[f.key] ?? ""} onChange={(e) => setMap(f.key, e.target.value)}>
                  <option value="">– not in the file –</option>
                  {heads.map(({ h, i }) => <option key={i} value={i} disabled={used.has(i) && cfg.mapping[f.key] !== i}>{h}</option>)}
                </select>
              </div>
            ))}
          </div>
          <div className="row small" style={{ gap: 14, flexWrap: "wrap", marginTop: 12 }}>
            {["marks", "fees", "payments"].includes(cfg.kind) && (
              <label className="row" style={{ gap: 6 }}>If no year column: <input style={{ width: 100 }} placeholder={up.year} value={cfg.year} onChange={(e) => set({ year: e.target.value })} /></label>
            )}
            {cfg.kind === "marks" && (
              <label className="row" style={{ gap: 6 }}>If no exam column:
                <select style={{ width: "auto" }} value={cfg.exam} onChange={(e) => set({ exam: e.target.value })}><option value="">–</option>{EXAMS.map((x) => <option key={x}>{x}</option>)}</select>
              </label>
            )}
            {["fees", "payments"].includes(cfg.kind) && (
              <label className="row" style={{ gap: 6 }}>If no payment mode:
                <select style={{ width: "auto" }} value={cfg.mode} onChange={(e) => set({ mode: e.target.value })}>{MODES.map((x) => <option key={x}>{x}</option>)}</select>
              </label>
            )}
            {["marks", "fees"].includes(cfg.kind) && (
              <label className="row" style={{ gap: 6 }}>If the system already has a different value:
                <select style={{ width: "auto" }} value={cfg.on_duplicate} onChange={(e) => set({ on_duplicate: e.target.value })}>
                  <option value="skip">keep the system value</option><option value="update">use the file's value</option>
                </select>
              </label>
            )}
          </div>
          {s.sample.length > 0 && (
            <div style={{ overflow: "auto", marginTop: 12 }}>
              <table className="small">
                <thead><tr>{s.headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
                <tbody>{s.sample.map((r, ri) => <tr key={ri}>{s.headers.map((_, i) => <td key={i}>{r[i] ?? ""}</td>)}</tr>)}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Report({ rep }) {
  return (
    <div className="stack" style={{ gap: 12 }}>
      {rep.blockers.map((b, i) => <div key={i} className="error"><AlertTriangle size={14} style={{ verticalAlign: -2 }} /> {b}</div>)}
      {rep.sheets.map((r) => (
        <div className="card" key={r.index}>
          <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
            <div><b>{r.name}</b> <span className="muted small">· {r.label} · {r.rows} rows read</span></div>
            <Counts r={r} />
          </div>
          {r.warnings.length > 0 && <ul className="small muted" style={{ margin: "8px 0 0" }}>{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
          {r.conflicts.length > 0 && (
            <div className="notice" style={{ marginTop: 10 }}>
              <b className="small">Different from what the system already has:</b>
              <ul className="small" style={{ margin: "4px 0 0" }}>{r.conflicts.map((c, i) => <li key={i}>{c}</li>)}</ul>
            </div>
          )}
          {r.errors.length > 0 && (
            <div className="card flush" style={{ maxHeight: 240, overflow: "auto", marginTop: 10 }}>
              <table>
                <thead><tr><th>Row</th><th>Who</th><th>Problem</th></tr></thead>
                <tbody>{r.errors.map((e, i) => <tr key={i}><td>{e.row}</td><td>{e.name || "–"}</td><td style={{ color: "var(--bad)" }}>{e.message}</td></tr>)}</tbody>
              </table>
              {r.error_count > r.errors.length && <p className="small muted" style={{ padding: "6px 12px" }}>…and {r.error_count - r.errors.length} more</p>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function History({ tick, bump }) {
  const state = useLoad(() => api("/import/batches"), [tick]);
  const [undo, setUndo] = useState(null);
  const [msg, setMsg] = useState("");
  return (
    <Async state={state}>
      {(rows) => rows.length === 0 ? null : (
        <div className="card flush" style={{ marginTop: 20 }}>
          <h3 style={{ padding: "14px 16px 0", margin: 0 }}>Earlier imports</h3>
          {msg && <div className="notice-ok" style={{ margin: 12 }}>{msg}</div>}
          <table>
            <thead><tr><th>When</th><th>File</th><th>By</th><th>Added</th><th /></tr></thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td>{when(b.at)}</td><td>{b.filename}</td><td>{b.by}</td>
                  <td className="small">{Object.entries(b.counts).map(([k, n]) => `${n} ${k}`).join(", ") || "only updates"}</td>
                  <td style={{ textAlign: "right" }}>
                    {b.undone ? <Badge>Undone</Badge> : b.can_undo
                      ? <button className="btn ghost sm" onClick={() => setUndo(b)}><RotateCcw size={14} /> Undo</button>
                      : <span className="muted small">Undo window ended</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {undo && (
            <Confirm title="Undo this import?" onClose={() => setUndo(null)}
              message={`This removes what "${undo.filename}" added (${Object.entries(undo.counts).map(([k, n]) => `${n} ${k}`).join(", ")}), including those students' logins, marks and fees, and puts back any value it changed. Anything added by hand in the meantime for those students is removed with them.`}
              onConfirm={async () => {
                try {
                  const r = await api(`/import/batches/${undo.id}/undo`, { method: "POST" });
                  setMsg(`Undone: ${Object.entries(r.removed).map(([k, n]) => `${n} ${k}`).join(", ") || "nothing to remove"}.`);
                  bump();
                } catch (x) { setMsg(x.message); }
                setUndo(null);
              }} />
          )}
        </div>
      )}
    </Async>
  );
}

/** Hand over existing school data (Excel, CSV, JSON, Word table). Review what was understood, check it, then confirm. */
export default function SmartImport() {
  const [up, setUp] = useState(null);
  const [cfg, setCfg] = useState([]);
  const [opts, setOpts] = useState({ logins: true, subjects: false });
  const [rep, setRep] = useState(null);
  const [done, setDone] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);

  const body = () => payload(cfg, opts);
  const setSheet = (i, patch) => { setRep(null); setCfg((c) => c.map((x, k) => (k === i ? { ...x, ...patch } : x))); };

  async function pick(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setErr(""); setRep(null); setDone(null);
    if (f.size > 5 * 1024 * 1024) return setErr("The file must be under 5 MB");
    setBusy(true);
    try { const r = await upload(f); setUp(r); setCfg(initial(r)); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  async function check() {
    setBusy(true); setErr("");
    try { setRep(await api(`/import/jobs/${up.job_id}/preview`, { method: "POST", body: body() })); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  async function confirm() {
    setBusy(true); setErr("");
    try { const r = await api(`/import/jobs/${up.job_id}/confirm`, { method: "POST", body: body() }); setDone(r); setTick((t) => t + 1); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  function reset() {
    if (up && !done) api(`/import/jobs/${up.job_id}`, { method: "DELETE" }).catch(() => {});
    setUp(null); setCfg([]); setRep(null); setDone(null); setErr("");
  }

  const chosen = cfg.filter((c) => c.include).length;
  return (
    <>
      <PageHead title="Smart import" sub="Bring in your existing records: students, staff, subjects, marks, fees, events and goals, from Excel, CSV, JSON or a Word table." />
      {done ? (
        <div className="card">
          {done.imported ? (
            <>
              <div className="notice-ok"><CheckCircle2 size={18} /> Imported: {Object.entries(done.totals).map(([k, n]) => `${n} ${k}`).join(", ") || "no new records"}
                {Object.keys(done.updated).length > 0 && `; updated ${Object.entries(done.updated).map(([k, n]) => `${n} ${k}`).join(", ")}`}.</div>
              {done.logins.length > 0 && (
                <>
                  <p className="muted"><b>Download this list now.</b> Each new person signs in with their ID and a one-time password, and must choose their own at first sign-in. The passwords are shown only once.</p>
                  <div className="card flush" style={{ maxHeight: 260, overflow: "auto" }}>
                    <table>
                      <thead><tr><th>Login ID</th><th>Name</th><th>Role</th><th>Temporary password</th></tr></thead>
                      <tbody>{done.logins.map((l) => <tr key={l.login}><td>{l.login}</td><td>{l.name}</td><td>{l.role}</td><td><code>{l.temp_password}</code></td></tr>)}</tbody>
                    </table>
                  </div>
                  <div className="modal-foot" style={{ justifyContent: "flex-start" }}><button className="btn ghost" onClick={() => saveCsv(done.logins)}>Download logins (CSV)</button></div>
                </>
              )}
            </>
          ) : (
            <div className="notice"><CheckCircle2 size={16} style={{ verticalAlign: -3 }} /> Everything in this file is already in the system, so nothing was added.</div>
          )}
          <div className="modal-foot" style={{ justifyContent: "flex-start" }}><button className="btn" onClick={reset}>Import another file</button></div>
        </div>
      ) : !up ? (
        <div className="card">
          <p className="muted">Upload one file. Every sheet (or table) is read, we work out what it holds and which column is which, and you review it before anything is saved.
            Nothing is changed until you confirm, the import is all-or-nothing, and you can undo it for 7 days.
            {" "}Records already in the system are recognised and not duplicated, so importing the same file twice is safe.</p>
          <ul className="muted small">
            <li>Start with students and subjects, then marks and fees in the same file or a later one (marks and fees find students by their old ID, or by name and class).</li>
            <li>Passwords are never imported. New students and staff get a one-time password to change at first sign-in.</li>
            <li>Up to 5 MB, 5,000 rows per sheet. Excel (.xlsx), CSV, JSON, Word (.docx) tables. Column headings may be sent to an AI service only if your platform team has set one up; the data itself never is.</li>
          </ul>
          <label className="btn" style={{ cursor: "pointer" }}><Upload size={16} /> {busy ? "Reading…" : "Choose file"}
            <input type="file" hidden onChange={pick} disabled={busy} accept=".xlsx,.csv,.json,.docx" />
          </label>
          {err && <div className="error" style={{ marginTop: 12 }}>{err}</div>}
        </div>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <div className="card row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div><FileUp size={16} style={{ verticalAlign: -3 }} /> <b>{up.filename}</b> <span className="muted small">· {up.sheets.length} sheet(s) found</span></div>
            <button className="btn ghost sm" onClick={reset}>Choose a different file</button>
          </div>
          {up.sheets.map((s, i) => <SheetCard key={s.index} s={s} up={up} cfg={cfg[i]} set={(p) => setSheet(i, p)} />)}
          <div className="card">
            <label className="row small" style={{ gap: 8 }}><input type="checkbox" style={{ width: "auto" }} checked={opts.logins} onChange={(e) => { setRep(null); setOpts({ ...opts, logins: e.target.checked }); }} /> Create sign-in logins for new students and staff</label>
            <label className="row small" style={{ gap: 8, marginTop: 6 }}><input type="checkbox" style={{ width: "auto" }} checked={opts.subjects} onChange={(e) => { setRep(null); setOpts({ ...opts, subjects: e.target.checked }); }} /> Create a subject if marks mention one the class does not have yet</label>
          </div>
          {err && <div className="error">{err}</div>}
          {rep && <Report rep={rep} />}
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <button className="btn ghost" onClick={check} disabled={busy || chosen === 0}>{busy && !rep ? "Checking…" : "Check the import"}</button>
            <button className="btn" onClick={confirm} disabled={busy || !rep || !rep.can_confirm}>
              {busy && rep ? "Importing…" : rep ? (rep.changes ? `Confirm and import` : "Nothing new to import") : "Confirm and import"}
            </button>
            {rep && !rep.can_confirm && <span className="small" style={{ color: "var(--bad)" }}>Fix the problems above (correct the file and upload again, or change the column choices).</span>}
          </div>
        </div>
      )}
      <History tick={tick} bump={() => setTick((t) => t + 1)} />
    </>
  );
}
