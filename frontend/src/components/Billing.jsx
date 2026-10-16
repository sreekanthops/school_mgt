import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { CheckCircle2, FilePlus2, XCircle } from "lucide-react";
import { api, inr } from "../api.js";
import { Async, Badge, Confirm, DownloadButton, FormModal, Modal, PageHead, Stat, useLoad } from "./ui.jsx";
import { SUB_KIND } from "../platform.js";

export const INV_KIND = { Paid: "good", Pending: "warn", Overdue: "bad", Cancelled: "gray" };
const MODES = ["Bank Transfer", "UPI", "Cheque", "Cash", "Card"];

const invoiceFields = (price) => [
  { key: "amount", label: `Amount before tax (suggested ${inr(price)})`, type: "number", min: 0, max: 100000000, default: price || "" },
  { key: "tax_pct", label: "Tax %", type: "number", min: 0, max: 100, default: 18 },
  { key: "period_start", label: "Service from (blank = after current end)", type: "date" },
  { key: "period_end", label: "Service until (blank = one year)", type: "date" },
  { key: "due_on", label: "Due date (blank = 15 days)", type: "date" },
  { key: "note", label: "Note on the invoice", type: "textarea", full: true },
];

const clean = (b) => Object.fromEntries(Object.entries(b).filter(([, v]) => v !== null && v !== ""));

export function NewInvoice({ school, price, onClose, onDone }) {
  return (
    <FormModal title={`New invoice · ${school.name || school.school}`} fields={invoiceFields(price)} submitLabel="Create invoice" onClose={onClose}
      onSubmit={async (b) => { await api(`/schools/${school.id ?? school.school_id}/invoices`, { method: "POST", body: clean(b) }); onDone(); }} />
  );
}

/** Pricing reference table shown in the billing console. */
function PricingTable({ table }) {
  if (!table?.length) return null;
  const plans = ["Starter", "Standard", "Premium"];
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2 style={{ marginBottom: 12 }}>Pricing reference — annual (before 18% GST)</h2>
      <p className="small muted" style={{ marginTop: 0, marginBottom: 12 }}>
        Invoice amounts are pre-filled from this table based on each school's plan and student limit.
        Monthly billing = annual ÷ 10 (2 months free vs paying monthly).
        You can always override the amount on any individual invoice.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Strength (students)</th>
              {plans.map((p) => <th key={p}>{p}</th>)}
              <th>Monthly ÷ 10</th>
            </tr>
          </thead>
          <tbody>
            {table.map((row) => (
              <tr key={row.band}>
                <td><b>{row.band}</b></td>
                {plans.map((p) => <td key={p}>{inr(row.plans[p])}</td>)}
                <td className="small muted">e.g. {inr(Math.round(row.plans["Standard"] / 10))}/mo (Standard)</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MarkPaid({ inv, onClose, onDone }) {
  const [f, setF] = useState({ mode: "Bank Transfer", reference: "", paid_on: "", extend: true });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function go(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api(`/invoices/${inv.id}/pay`, { method: "PUT", body: clean({ ...f }) }); onDone(); onClose(); } catch (x) { setErr(x.message); setBusy(false); }
  }
  return (
    <Modal title={`Record payment · ${inv.number}`} onClose={onClose}>
      <form onSubmit={go}>
        {err && <div className="error">{err}</div>}
        <p>Total <b>{inr(inv.total)}</b> for {inv.school_name}, service {inv.period_start} to {inv.period_end}.</p>
        <div className="form-grid">
          <div className="field"><label htmlFor="pm">Payment mode</label>
            <select id="pm" value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>{MODES.map((m) => <option key={m}>{m}</option>)}</select></div>
          <div className="field"><label htmlFor="pr">Reference (UTR / cheque no.)</label>
            <input id="pr" maxLength={60} value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></div>
          <div className="field"><label htmlFor="pd">Paid on (blank = today)</label>
            <input id="pd" type="date" value={f.paid_on} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setF({ ...f, paid_on: e.target.value })} /></div>
          <label className="check" style={{ gridColumn: "1 / -1" }}>
            <input type="checkbox" checked={f.extend} onChange={(e) => setF({ ...f, extend: e.target.checked })} /> Extend the subscription to {inv.period_end}
          </label>
        </div>
        <div className="modal-foot"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn" disabled={busy}>{busy ? "Saving…" : "Mark as paid"}</button></div>
      </form>
    </Modal>
  );
}

export function InvoiceTable({ rows, onChange, showSchool = true }) {
  const [paying, setPaying] = useState(null);
  const [cancel, setCancel] = useState(null);
  return (
    <>
      {paying && <MarkPaid inv={paying} onClose={() => setPaying(null)} onDone={onChange} />}
      {cancel && <Confirm title="Cancel invoice" message={`Cancel ${cancel.number}? It will stay on record as cancelled.`} onClose={() => setCancel(null)}
        onConfirm={async () => { await api(`/invoices/${cancel.id}/cancel`, { method: "PUT" }); onChange(); }} />}
      <div className="card flush" style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>Invoice</th>{showSchool && <th>School</th>}<th>Service period</th><th>Total</th><th>Due</th><th>Status</th><th /></tr></thead>
          <tbody>
            {rows.map((i) => (
              <tr key={i.id}>
                <td><b>{i.number}</b><div className="small muted">{i.plan} · issued {i.issued_on}</div></td>
                {showSchool && <td>{i.school_name}</td>}
                <td className="small">{i.period_start} → {i.period_end}</td>
                <td>{inr(i.total)}<div className="small muted">{inr(i.amount)} + {inr(i.tax)} tax</div></td>
                <td className="small">{i.paid_on ? `Paid ${i.paid_on}` : i.due_on}{i.mode && <div className="muted">{i.mode}{i.reference ? ` · ${i.reference}` : ""}</div>}</td>
                <td><Badge kind={INV_KIND[i.status]}>{i.status}</Badge></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <DownloadButton path={`/invoices/${i.id}/pdf`} label="PDF" />{" "}
                  {(i.status === "Pending" || i.status === "Overdue") && (
                    <>
                      <button className="btn sm" onClick={() => setPaying(i)}><CheckCircle2 size={13} /> Mark paid</button>{" "}
                      <button className="btn danger sm" onClick={() => setCancel(i)}><XCircle size={13} /> Cancel</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={7} className="empty">No invoices.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Platform Console → Billing tab: collection stats, renewal tracking and all invoices. */
export default function Billing() {
  const [tick, setTick] = useState(0);
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(null);
  const refresh = () => setTick((t) => t + 1);
  const sum = useLoad(() => api("/billing/summary"), [tick]);
  const list = useLoad(() => api(`/invoices${filter ? `?status=${filter}` : ""}`), [tick, filter]);
  return (
    <Async state={sum}>
      {(s) => (
        <>
          {creating && <NewInvoice school={creating} price={creating.suggested_price ?? 0} onClose={() => setCreating(null)} onDone={refresh} />}
          <div className="grid g4" style={{ marginBottom: 16 }}>
            <Stat label="Collected" value={inr(s.collected)} tint="green" />
            <Stat label="Awaiting payment" value={inr(s.pending)} tint="amber" />
            <Stat label="Overdue" value={inr(s.overdue)} sub={`${s.overdue_count} invoice${s.overdue_count === 1 ? "" : "s"}`} tint="rose" />
            <Stat label="Invoices issued" value={s.invoices} tint="indigo" />
          </div>
          <div className="grid g2" style={{ marginBottom: 16 }}>
            <div className="card">
              <h2>Collected per month</h2>
              <ResponsiveContainer width="100%" height={210}>
                <BarChart data={s.monthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" fontSize={11} tickFormatter={(v) => v.slice(2)} /><YAxis fontSize={11} tickFormatter={(v) => `${v / 1000}k`} />
                  <Tooltip formatter={(v) => inr(v)} /><Bar dataKey="amount" name="Collected" fill="#16a34a" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="card">
              <h2>Renewals</h2>
              <div className="small muted" style={{ marginBottom: 6 }}>Nearest subscription end first. Raise an invoice before it ends.</div>
              <div style={{ maxHeight: 210, overflow: "auto" }}>
                {s.renewals.map((r) => (
                  <div key={r.school_id} className="row" style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                    <div><Link to={`/schools/${r.school_id}`}><b>{r.school}</b></Link>
                      <div className="small muted">{r.end ? `${r.end} · ${r.days_left < 0 ? `${-r.days_left} days ago` : `${r.days_left} days left`}` : "No expiry"}</div></div>
                    <div className="row" style={{ gap: 6 }}>
                      <Badge kind={SUB_KIND[r.status]}>{r.status}</Badge>
                      {r.invoice_open ? <Badge kind="warn">Invoice open</Badge>
                        : <button className="btn ghost sm" onClick={() => setCreating({ id: r.school_id, name: r.school, plan: r.plan, suggested_price: r.suggested_price })}><FilePlus2 size={13} /> Invoice</button>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <PricingTable table={s.pricing_table} />
          <div className="toolbar">
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Status">
              <option value="">All invoices</option>{["Pending", "Overdue", "Paid", "Cancelled"].map((x) => <option key={x}>{x}</option>)}
            </select>
            <DownloadButton path="/invoices/export" label="Export CSV" />
          </div>
          <Async state={list}>{(rows) => <InvoiceTable rows={rows} onChange={refresh} />}</Async>
        </>
      )}
    </Async>
  );
}

/** Owner's own school: invoices, read-only. */
export function MyBilling() {
  const state = useLoad(() => api("/billing/mine"));
  return (
    <>
      <PageHead title="Billing" sub="Your subscription and invoices from the platform team" />
      <Async state={state}>
        {(d) => (
          <>
            <div className="grid g3" style={{ marginBottom: 16 }}>
              <Stat label="Plan" value={d.plan} tint="indigo" />
              <Stat label="Subscription" value={d.subscription.status} sub={d.subscription.end ? `ends ${d.subscription.end}` : "no end date"} tint="green" />
              <Stat label="Days left" value={d.subscription.days_left ?? "–"} tint="amber" />
            </div>
            <div className="card flush" style={{ overflowX: "auto" }}>
              <table>
                <thead><tr><th>Invoice</th><th>Service period</th><th>Total</th><th>Due</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {d.invoices.map((i) => (
                    <tr key={i.id}>
                      <td><b>{i.number}</b><div className="small muted">issued {i.issued_on}</div></td>
                      <td className="small">{i.period_start} → {i.period_end}</td>
                      <td>{inr(i.total)}</td>
                      <td className="small">{i.paid_on ? `Paid ${i.paid_on}` : i.due_on}</td>
                      <td><Badge kind={INV_KIND[i.status]}>{i.status}</Badge></td>
                      <td><DownloadButton path={`/billing/mine/${i.id}/pdf`} label="PDF" /></td>
                    </tr>
                  ))}
                  {d.invoices.length === 0 && <tr><td colSpan={6} className="empty">No invoices yet.</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="muted small" style={{ marginTop: 10 }}>To renew or change plan, contact the platform team.</p>
          </>
        )}
      </Async>
    </>
  );
}
