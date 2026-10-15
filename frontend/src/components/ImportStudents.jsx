import { useState } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { ApiError, download, getSession } from "../api.js";
import { Badge, Modal } from "./ui.jsx";

async function send(file, dryRun) {
  const res = await fetch(`/api/students/import?dry_run=${dryRun}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", Authorization: `Bearer ${getSession()?.token}` },
    body: file,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new ApiError(res.status, typeof data?.detail === "string" ? data.detail : "The file could not be imported");
  return data;
}

// names are user-entered: a leading = + - @ would run as a formula in a spreadsheet, so it is defused (passwords are server-generated and kept exact)
const cell = (v) => `"${(/^[=+\-@\t\r]/.test(v) ? "'" + v : v).replace(/"/g, '""')}"`;
const csvOf = (logins) =>
  ["Student ID (login),Name,Class,Temporary password", ...logins.map((l) => [l.student_id, cell(l.name), l.class, l.temp_password].join(","))].join("\n");

/** Upload a CSV/Excel sheet, review it, then import. Nothing is saved until the review shows no problems. */
export default function ImportStudents({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [review, setReview] = useState(null);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function pick(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setErr(""); setReview(null); setFile(null);
    if (f.size > 2 * 1024 * 1024) return setErr("The file must be under 2 MB");
    setBusy(true);
    try { setReview(await send(f, true)); setFile(f); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  async function run() {
    setBusy(true); setErr("");
    try { const r = await send(file, false); setDone(r); onDone(); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  function save() {
    const url = URL.createObjectURL(new Blob(["\ufeff" + csvOf(done.logins)], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "new-student-logins.csv" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  if (done) {
    return (
      <Modal title={`${done.imported} students imported`} onClose={onClose} wide>
        <div className="notice-ok"><CheckCircle2 size={18} /> Each student now has a login (their Student ID) and a one-time password. They must choose their own password at first sign-in.</div>
        <p className="muted"><b>Download this list now.</b> The passwords are shown only once and cannot be recovered afterwards.</p>
        <div className="card flush" style={{ maxHeight: 280, overflow: "auto" }}>
          <table>
            <thead><tr><th>Student ID</th><th>Name</th><th>Class</th><th>Temporary password</th></tr></thead>
            <tbody>{done.logins.map((l) => <tr key={l.student_id}><td>{l.student_id}</td><td>{l.name}</td><td>{l.class}</td><td><code>{l.temp_password}</code></td></tr>)}</tbody>
          </table>
        </div>
        <div className="modal-foot"><button className="btn ghost" onClick={save}>Download logins (CSV)</button><button className="btn" onClick={onClose}>Done</button></div>
      </Modal>
    );
  }

  return (
    <Modal title="Import students from a spreadsheet" onClose={onClose} wide>
      <p className="muted">Upload a CSV or Excel (.xlsx) file, one student per row, up to 300 rows. Required columns: name, gender, dob, class, section, guardian_name, phone.
        Optional: email, blood_group, address. Student IDs and logins are created automatically.</p>
      <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
        <label className="btn" style={{ cursor: "pointer" }}>
          <Upload size={16} /> {busy ? "Checking…" : file ? "Choose a different file" : "Choose file"}
          <input type="file" hidden accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={pick} disabled={busy} />
        </label>
        <button type="button" className="btn ghost" onClick={() => download("/students/import/template", "students-template.csv").catch((x) => setErr(x.message))}>
          <FileSpreadsheet size={16} /> Download template
        </button>
        {file && <span className="muted small">{file.name}</span>}
      </div>
      {err && <div className="error" style={{ marginTop: 12 }}>{err}</div>}
      {review && (
        <div style={{ marginTop: 16 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <Badge kind="good">{review.valid} ready</Badge>
            {review.errors.length > 0 && <Badge kind="bad">{review.errors.length} need fixing</Badge>}
            <span className="muted small">{review.rows} rows read</span>
          </div>
          {review.errors.length > 0 && (
            <div className="card flush" style={{ maxHeight: 220, overflow: "auto", marginTop: 10 }}>
              <table>
                <thead><tr><th>Row</th><th>Student</th><th>Problem</th></tr></thead>
                <tbody>{review.errors.map((e) => <tr key={e.row}><td>{e.row}</td><td>{e.name || "–"}</td><td style={{ color: "var(--bad)" }}>{e.message}</td></tr>)}</tbody>
              </table>
            </div>
          )}
          {review.errors.length === 0 && review.preview.length > 0 && (
            <ul className="muted small" style={{ marginTop: 10 }}>
              {review.preview.map((p, i) => <li key={i}>{p.name} · Class {p.class} · {p.guardian}</li>)}
              {review.valid > review.preview.length && <li>…and {review.valid - review.preview.length} more</li>}
            </ul>
          )}
          {review.errors.length > 0 && <p className="small"><AlertTriangle size={14} style={{ verticalAlign: -2 }} /> Nothing is imported until every row is fixed. Correct the file and choose it again.</p>}
        </div>
      )}
      <div className="modal-foot">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn" onClick={run} disabled={busy || !review || review.errors.length > 0 || review.valid === 0}>
          {busy && review ? "Importing…" : `Import ${review?.valid ?? ""} students`}
        </button>
      </div>
    </Modal>
  );
}
