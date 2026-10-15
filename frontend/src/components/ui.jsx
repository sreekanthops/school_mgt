import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Download, X } from "lucide-react";
import { download, fetchImage, upload } from "../api.js";

export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: e.message, loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function Async({ state, children }) {
  if (state.loading && !state.data) return <div className="empty">Loading…</div>;
  if (state.error) return <div className="error">{state.error}</div>;
  return children(state.data);
}

export const Stat = ({ label, value, sub, icon: Icon, tint = "indigo", to }) => {
  const nav = useNavigate();
  const go = to ? () => nav(to) : undefined;
  return (
    <div className={`card stat ${to ? "link" : ""}`} onClick={go} role={to ? "link" : undefined} tabIndex={to ? 0 : undefined}
      onKeyDown={to ? (e) => e.key === "Enter" && go() : undefined}>
      {Icon && <span className={`stat-icon ${tint}`}><Icon size={20} /></span>}
      <div>
        <div className="label">{label}</div>
        <div className="value">{value}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
    </div>
  );
};

export const tone = (p) => (p == null ? "" : p >= 75 ? "good" : p >= 50 ? "warn" : "bad");
export const Badge = ({ children, kind = "" }) => <span className={`badge ${kind}`}>{children}</span>;
export const Meter = ({ pct, kind }) => (
  <div className={`bar ${kind ?? tone(pct)}`}><i style={{ width: `${Math.max(0, Math.min(100, pct ?? 0))}%` }} /></div>
);

export const PageHead = ({ title, sub, children }) => (
  <div className="page-head">
    <div><h1>{title}</h1>{sub && <div className="muted">{sub}</div>}</div>
    <div className="actions">{children}</div>
  </div>
);

/** Round photo with initials fallback. `kind`: students | staff. */
export function Photo({ kind, id, name, v, has, size = 38, path, square }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url;
    let alive = true;
    setSrc(null);
    if (has) {
      fetchImage(path ?? `/${kind}/${id}/photo`).then((u) => {
        url = u;
        if (alive) setSrc(u);
      });
    }
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [kind, id, v, has, path]);
  const initials = (name || "?").split(" ").map((p) => p[0]).slice(0, 2).join("");
  if (square) return src ? <img src={src} alt={name} /> : <div className="pic" style={{ background: "#eceff7" }} />;
  return src
    ? <img className="avatar-img" src={src} alt={name} style={{ width: size, height: size }} />
    : <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.36 }}>{initials}</span>;
}

/** Click-to-upload button for an image path. */
export function PhotoUpload({ path, label = "Change photo", onDone }) {
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function pick(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 3 * 1024 * 1024) return setErr("Image must be under 3 MB");
    setBusy(true);
    setErr("");
    try {
      await upload(path, f);
      onDone?.();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <label className="btn ghost sm" style={{ cursor: "pointer" }}>
        <Camera size={14} /> {busy ? "Uploading…" : label}
        <input type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={pick} disabled={busy} />
      </label>
      {err && <div className="small" style={{ color: "var(--bad)", marginTop: 4 }}>{err}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const h = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={onClose}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        {children}
      </div>
    </div>
  );
}

/** Generic form dialog. fields: [{key,label,type,options,required,full}] */
export function FormModal({ title, fields, initial, onSubmit, onClose, submitLabel = "Save" }) {
  const [f, setF] = useState(() => Object.fromEntries(fields.map((x) => [x.key, initial?.[x.key] ?? x.default ?? ""])));
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const body = {};
      fields.forEach((x) => {
        let v = f[x.key];
        if (x.type === "number") v = v === "" ? null : Number(v);
        else if (v === "" && !x.required) v = null;
        body[x.key] = v;
      });
      await onSubmit(body);
      onClose();
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={title} onClose={onClose} wide>
      <form onSubmit={submit}>
        {err && <div className="error">{err}</div>}
        <div className="form-grid">
          {fields.map((x) => (
            <div key={x.key} className="field" style={x.full ? { gridColumn: "1 / -1" } : undefined}>
              <label htmlFor={`f-${x.key}`}>{x.label}{x.required && " *"}</label>
              {x.type === "select" ? (
                <select id={`f-${x.key}`} value={f[x.key] ?? ""} onChange={(e) => setF({ ...f, [x.key]: e.target.value })}>
                  {x.options.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o || "—"]; return <option key={v} value={v}>{l}</option>; })}
                </select>
              ) : x.type === "textarea" ? (
                <textarea id={`f-${x.key}`} rows={3} value={f[x.key] ?? ""} onChange={(e) => setF({ ...f, [x.key]: e.target.value })} required={x.required} />
              ) : (
                <input id={`f-${x.key}`} type={x.type || "text"} value={f[x.key] ?? ""} min={x.min} max={x.max}
                  onChange={(e) => setF({ ...f, [x.key]: e.target.value })} required={x.required} />
              )}
            </div>
          ))}
        </div>
        <div className="modal-foot"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn" disabled={busy}>{busy ? "Saving…" : submitLabel}</button></div>
      </form>
    </Modal>
  );
}

export function Confirm({ title, message, onConfirm, onClose, danger = true }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true);
    try { await onConfirm(); onClose(); } catch (x) { setErr(x.message); setBusy(false); }
  }
  return (
    <Modal title={title} onClose={onClose}>
      {err && <div className="error">{err}</div>}
      <p>{message}</p>
      <div className="modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className={`btn ${danger ? "danger-solid" : ""}`} onClick={go} disabled={busy}>{busy ? "Working…" : "Confirm"}</button>
      </div>
    </Modal>
  );
}

/** Shows a credential once (temp password) with a copy button. */
export function Secret({ title, username, password, idLabel = "Username", onClose }) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="muted">Share these with the user securely. The password is shown only once; they should change it after the first login.</p>
      <dl className="kv"><dt>{idLabel}</dt><dd><b>{username}</b></dd><dt>Temporary password</dt><dd><code>{password}</code></dd></dl>
      <div className="modal-foot">
        <button className="btn ghost" onClick={() => navigator.clipboard?.writeText(`${username} / ${password}`)}>Copy</button>
        <button className="btn" onClick={onClose}>Done</button>
      </div>
    </Modal>
  );
}

export const Empty = ({ children }) => <div className="empty">{children}</div>;

/** Button that downloads a file from an API path. `keep` keeps it usable when the school is read-only (downloads are reads). */
export function DownloadButton({ path, label, name, icon = true, className = "btn ghost sm" }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true);
    setErr("");
    try { await download(path, name); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  return (
    <span style={{ display: "inline-flex", flexDirection: "column" }}>
      <button type="button" className={`${className} keep`} onClick={go} disabled={busy}>
        {icon && <Download size={14} />} {busy ? "Preparing…" : label}
      </button>
      {err && <span className="small" style={{ color: "var(--bad)" }}>{err}</span>}
    </span>
  );
}

/** "Export" pair: CSV and PDF of the same data. */
export const ExportButtons = ({ base, params = "", what }) => (
  <>
    <DownloadButton path={`${base}?format=csv${params}`} label={`${what} CSV`} />
    <DownloadButton path={`${base}?format=pdf${params}`} label="PDF" />
  </>
);
