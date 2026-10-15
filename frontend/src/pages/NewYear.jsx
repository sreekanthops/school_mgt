import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CalendarClock, GraduationCap } from "lucide-react";
import { api, gradeLabel } from "../api.js";
import { Async, Badge, Confirm, PageHead, useLoad } from "../components/ui.jsx";

/** Start the next academic year: everyone moves up one class, except students you choose to hold back. */
export default function NewYear() {
  const [tick, setTick] = useState(0);
  const [held, setHeld] = useState(new Set());
  const [openG, setOpenG] = useState(null);
  const [removeGrads, setRemoveGrads] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState(null);
  const state = useLoad(() => api("/school/new-year"), [tick]);
  const toggle = (id) => setHeld((h) => { const n = new Set(h); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <Async state={state}>
      {(d) => {
        const total = d.grades.reduce((n, g) => n + g.students.length, 0);
        const last = d.grades[d.grades.length - 1];
        if (result) {
          return (
            <>
              <PageHead title="New academic year started" sub={`Now in ${result.year}`} />
              <div className="card">
                <p><b>{result.promoted}</b> students moved up a class. <b>{result.held_back}</b> were held back.
                  {result.class10_removed > 0 && <> <b>{result.class10_removed}</b> Class 10 students were removed.</>}
                  {result.class10_remaining > 0 && <> <b>{result.class10_remaining}</b> Class 10 students stay in Class 10 until you remove them.</>}</p>
                <p className="muted">Last year's marks, fees and payments are kept and can be picked from the year drop-down on each student. Next: set the new year's fees from the Fees page and add the new LKG admissions.</p>
                <Link className="btn" to="/fees">Go to fees</Link>
              </div>
            </>
          );
        }
        return (
          <>
            <Link to="/students" className="backlink"><ArrowLeft size={14} /> Students</Link>
            <PageHead title="Start new academic year" sub={`Move from ${d.current_year} to ${d.next_year}`} />
            <div className="card" style={{ marginBottom: 16 }}>
              <h2><CalendarClock size={18} style={{ verticalAlign: -3 }} /> What happens</h2>
              <ul>
                <li>Every student moves up one class (LKG → UKG → Class 1 … → Class 10). Their section stays the same.</li>
                <li>Student IDs and logins do <b>not</b> change.</li>
                <li>Marks, fees and payments of {d.current_year} stay on record and remain viewable.</li>
                <li>Students you tick below are <b>held back</b> and stay in their current class.</li>
                <li>This can only be done once for {d.next_year}.</li>
              </ul>
              <label className="check"><input type="checkbox" checked={removeGrads} onChange={(e) => setRemoveGrads(e.target.checked)} />
                {" "}Remove Class 10 students who finish this year ({last.students.length - last.students.filter((s) => held.has(s.id)).length}). This deletes their records.</label>
            </div>
            <div className="card flush">
              <table>
                <thead><tr><th>Class</th><th>Students</th><th>Moves to</th><th>Held back</th><th /></tr></thead>
                <tbody>
                  {d.grades.map((g) => {
                    const h = g.students.filter((s) => held.has(s.id)).length;
                    return (
                      <FragmentRow key={g.grade} g={g} h={h} open={openG === g.grade} setOpen={() => setOpenG(openG === g.grade ? null : g.grade)}
                        held={held} toggle={toggle} passMark={d.pass_mark} />
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="row" style={{ marginTop: 16, justifyContent: "space-between" }}>
              <span className="muted">{total} students · {held.size} held back</span>
              <button className="btn" disabled={total === 0} onClick={() => setConfirm(true)}><GraduationCap size={16} /> Start {d.next_year}</button>
            </div>
            {confirm && (
              <Confirm danger={removeGrads} title={`Start ${d.next_year}?`} onClose={() => setConfirm(false)}
                message={`${total - held.size} of ${total} students will move up and ${held.size} will be held back.${removeGrads ? " Class 10 leavers will be deleted." : ""} This cannot be undone.`}
                onConfirm={async () => {
                  setResult(await api("/school/new-year", { method: "POST", body: { year: d.next_year, hold_back: [...held], remove_graduates: removeGrads } }));
                  setTick((t) => t + 1);
                }} />
            )}
          </>
        );
      }}
    </Async>
  );
}

function FragmentRow({ g, h, open, setOpen, held, toggle, passMark }) {
  return (
    <>
      <tr className="click" onClick={setOpen}>
        <td><b>{gradeLabel(g.grade)}</b></td>
        <td>{g.students.length}</td>
        <td>{g.next ? gradeLabel(g.next) : <span className="muted">Leaves school</span>}</td>
        <td>{h > 0 ? <Badge kind="warn">{h}</Badge> : <span className="muted">–</span>}</td>
        <td className="muted small">{g.students.length ? (open ? "Hide students" : "Choose who to hold back") : ""}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} style={{ background: "var(--bg)" }}>
            <div className="chip-list">
              {g.students.map((s) => (
                <label key={s.id} className="chip" style={{ cursor: "pointer", background: held.has(s.id) ? "#fef3c7" : undefined }}>
                  <input type="checkbox" checked={held.has(s.id)} onChange={() => toggle(s.id)} /> {s.name} ({g.grade}-{s.section})
                  {s.overall_pct != null && <span className={s.overall_pct < passMark ? "bad-text" : "muted"}> · {s.overall_pct}%</span>}
                </label>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
