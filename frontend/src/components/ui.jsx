import { useEffect, useState } from "react";

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
  if (state.loading) return <div className="empty">Loading…</div>;
  if (state.error) return <div className="error">{state.error}</div>;
  return children(state.data);
}

export const Stat = ({ label, value, sub }) => (
  <div className="card stat">
    <div className="label">{label}</div>
    <div className="value">{value}</div>
    {sub && <div className="sub">{sub}</div>}
  </div>
);

export const tone = (p) => (p == null ? "" : p >= 75 ? "good" : p >= 50 ? "warn" : "bad");

export const Badge = ({ children, kind = "" }) => <span className={`badge ${kind}`}>{children}</span>;

export const Bar = ({ pct, kind }) => (
  <div className={`bar ${kind ?? tone(pct)}`}><i style={{ width: `${Math.max(0, Math.min(100, pct ?? 0))}%` }} /></div>
);

export const Avatar = ({ name, lg }) => (
  <span className={`avatar ${lg ? "lg" : ""}`}>{name.split(" ").map((p) => p[0]).slice(0, 2).join("")}</span>
);

export const PageHead = ({ title, sub, children }) => (
  <div className="page-head">
    <div><h1>{title}</h1>{sub && <div className="muted">{sub}</div>}</div>
    <div>{children}</div>
  </div>
);
