import { api } from "../api.js";
import { Async, PageHead, useLoad } from "../components/ui.jsx";

export default function About() {
  const state = useLoad(() => api("/about"));
  return (
    <>
      <PageHead title="About" />
      <Async state={state}>
        {(a) => (
          <div className="grid g2">
            <div className="card" style={{ gridColumn: "1 / -1" }}>
              <h2>{a.name}</h2>
              <p>{a.about}</p>
              <div className="small muted">Founded {a.founded}</div>
            </div>
            <div className="card"><h2>Mission</h2><p>{a.mission}</p></div>
            <div className="card"><h2>Vision</h2><p>{a.vision}</p></div>
            <div className="card"><h2>Contact</h2><p>{a.address}</p><p>{a.contact}</p></div>
          </div>
        )}
      </Async>
    </>
  );
}
