import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Mail, Pencil, Phone, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { staffFields } from "../forms.js";
import { Async, Badge, Confirm, FormModal, Photo, PhotoUpload, useLoad } from "../components/ui.jsx";

export default function StaffDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [tick, setTick] = useState(0);
  const [dlg, setDlg] = useState(null);
  const state = useLoad(() => api(`/staff/${id}`), [id, tick]);
  const reload = () => setTick((t) => t + 1);

  return (
    <Async state={state}>
      {(s) => (
        <>
          <Link to="/staff" className="backlink"><ArrowLeft size={14} /> Staff</Link>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="hero-cover" />
            <div className="hero">
              <Photo kind="staff" id={s.id} name={s.name} has={s.has_photo} v={s.photo_v} size={110} />
              <div style={{ flex: 1, minWidth: 220, paddingTop: 10 }}>
                <h1 style={{ margin: 0 }}>{s.name}</h1>
                <div className="muted">{s.designation} · {s.department}</div>
                <div className="chip-list" style={{ marginTop: 8 }}>
                  {s.class_teacher_of && <span className="chip">Class teacher {s.class_teacher_of}</span>}
                  <span className="chip">{s.experience_years} yrs experience</span>
                </div>
              </div>
              <div className="actions">
                {s.can.photo && <PhotoUpload path={`/staff/${s.id}/photo`} onDone={reload} />}
                {s.can.edit && <button className="btn ghost sm" onClick={() => setDlg("edit")}><Pencil size={14} /> Edit</button>}
                {s.can.edit && <button className="btn danger sm" onClick={() => setDlg("del")}><Trash2 size={14} /> Delete</button>}
              </div>
            </div>
          </div>
          <div className="grid g2">
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Details</h3>
              <dl className="kv">
                <dt>Staff ID</dt><dd>{s.employee_id}</dd>
                <dt>Gender</dt><dd>{s.gender}</dd>
                <dt>Qualification</dt><dd>{s.qualification}</dd>
                <dt>Joined</dt><dd>{s.joined_on}</dd>
                <dt>Phone</dt><dd><Phone size={13} /> {s.phone}</dd>
                <dt>Email</dt><dd><Mail size={13} /> {s.email}</dd>
              </dl>
            </div>
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Teaching</h3>
              {s.teaches.length === 0 && <div className="muted">{s.subjects || "No subjects assigned."}</div>}
              <div className="chip-list">
                {s.teaches.map((t) => (
                  <Link key={t.id} to={`/subjects/${t.id}`} className="chip">{t.name} · {t.grade}</Link>
                ))}
              </div>
              {s.bio && (<><h3>About</h3><p className="muted">{s.bio}</p></>)}
            </div>
          </div>
          {dlg === "edit" && (
            <FormModal title="Edit staff member" fields={staffFields} initial={s} onClose={() => setDlg(null)}
              onSubmit={async (b) => { await api(`/staff/${s.id}`, { method: "PUT", body: b }); reload(); }} />
          )}
          {dlg === "del" && (
            <Confirm title="Delete staff member" message={`Delete ${s.name}? Linked logins will lose their staff link.`}
              onClose={() => setDlg(null)} onConfirm={async () => { await api(`/staff/${s.id}`, { method: "DELETE" }); nav("/staff"); }} />
          )}
        </>
      )}
    </Async>
  );
}
