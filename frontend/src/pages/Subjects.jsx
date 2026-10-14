import { useState } from "react";
import { api, gradeLabel } from "../api.js";
import { Async, PageHead, useLoad } from "../components/ui.jsx";

export default function Subjects() {
  const state = useLoad(() => api("/subjects"));
  const [sel, setSel] = useState("LKG");
  return (
    <>
      <PageHead title="Subjects" sub="Curriculum for every class from LKG to Class 10" />
      <Async state={state}>
        {(rows) => {
          const cur = rows.find((r) => r.grade === sel) ?? rows[0];
          return (
            <>
              <div className="tabs">
                {rows.map((r) => <button key={r.grade} className={r.grade === sel ? "on" : ""} onClick={() => setSel(r.grade)}>{gradeLabel(r.grade)}</button>)}
              </div>
              <div className="grid g3">
                {cur.subjects.map((s) => (
                  <div key={s.id} className="card">
                    <h2>{s.name}</h2>
                    <div className="small muted">Teachers</div>
                    <div>{s.teachers.length ? s.teachers.join(", ") : <span className="muted">Unassigned</span>}</div>
                  </div>
                ))}
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
