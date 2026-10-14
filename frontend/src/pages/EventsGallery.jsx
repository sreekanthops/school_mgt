import { useState } from "react";
import { api } from "../api.js";
import { Async, Badge, PageHead, useLoad } from "../components/ui.jsx";

const PALETTE = ["#4f46e5", "#0ea5e9", "#16a34a", "#f59e0b", "#e11d48", "#8b5cf6", "#14b8a6", "#f97316"];
const hue = (s) => PALETTE[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length];

export default function EventsGallery() {
  const events = useLoad(() => api("/events"));
  const gallery = useLoad(() => api("/gallery"));
  const [cat, setCat] = useState("All");
  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <PageHead title="Events & Gallery" sub="What's happening and moments from school life" />
      <h2>Events</h2>
      <Async state={events}>
        {(rows) => (
          <div className="grid g2" style={{ marginBottom: 24 }}>
            {rows.map((e) => (
              <div key={e.id} className="card row" style={{ alignItems: "flex-start" }}>
                <div className="timeline-date">{e.date.slice(8)}<div className="small">{new Date(e.date).toLocaleString("en", { month: "short" })}</div></div>
                <div>
                  <b>{e.title}</b> <Badge kind={e.date >= today ? "good" : ""}>{e.date >= today ? "Upcoming" : "Past"}</Badge>
                  <div className="small muted">{e.category} · {e.location}</div>
                  <div style={{ marginTop: 4 }}>{e.description}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Async>
      <h2>Gallery</h2>
      <Async state={gallery}>
        {(items) => {
          const cats = ["All", ...new Set(items.map((i) => i.category))];
          return (
            <>
              <div className="tabs">{cats.map((c) => <button key={c} className={c === cat ? "on" : ""} onClick={() => setCat(c)}>{c}</button>)}</div>
              <div className="gallery">
                {items.filter((i) => cat === "All" || i.category === cat).map((i) => (
                  <div key={i.id} className="tile">
                    {i.image_url
                      ? <img src={i.image_url} alt={i.title} style={{ width: "100%", height: 140, objectFit: "cover" }} />
                      : <div className="pic" style={{ background: `linear-gradient(135deg, ${hue(i.title)}, ${hue(i.category)}aa)` }}>{i.category}</div>}
                    <div className="meta"><b>{i.title}</b><div className="small muted">{i.caption}</div><div className="small muted">{i.taken_on}</div></div>
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
