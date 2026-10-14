import { api } from "../api.js";
import { Async, Badge, Bar, PageHead, useLoad } from "../components/ui.jsx";

export default function Goals() {
  const state = useLoad(() => api("/goals"));
  return (
    <>
      <PageHead title="Future Goals" sub="Where the school is heading" />
      <Async state={state}>
        {(rows) => (
          <div className="grid g2">
            {rows.map((g) => (
              <div key={g.id} className="card">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <h2 style={{ margin: 0 }}>{g.title}</h2><Badge kind={g.status === "In Progress" ? "warn" : ""}>{g.status}</Badge>
                </div>
                <p className="muted">{g.description}</p>
                <Bar pct={g.progress} kind="" />
                <div className="small muted" style={{ marginTop: 4 }}>{g.progress}% complete · target {g.target_year}</div>
              </div>
            ))}
          </div>
        )}
      </Async>
    </>
  );
}
