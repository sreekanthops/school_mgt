import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import {
  BookOpen, Building2, CalendarDays, GraduationCap, Images, Info, KeyRound, LayoutDashboard, LogOut, Menu,
  ShieldCheck, Target, UserCircle, Users, Wallet, Camera, GraduationCap as Logo,
} from "lucide-react";
import { api } from "./api.js";
import { useAuth } from "./auth.jsx";
import Chatbot from "./components/Chatbot.jsx";
import { Photo } from "./components/ui.jsx";
import Login from "./pages/Login.jsx";

const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const Students = lazy(() => import("./pages/Students.jsx"));
const StudentDetail = lazy(() => import("./pages/StudentDetail.jsx"));
const Fees = lazy(() => import("./pages/Fees.jsx"));
const Subjects = lazy(() => import("./pages/Subjects.jsx"));
const SubjectDetail = lazy(() => import("./pages/SubjectDetail.jsx"));
const Staff = lazy(() => import("./pages/Staff.jsx"));
const StaffDetail = lazy(() => import("./pages/StaffDetail.jsx"));
const Events = lazy(() => import("./pages/Events.jsx"));
const Gallery = lazy(() => import("./pages/Gallery.jsx"));
const Goals = lazy(() => import("./pages/Goals.jsx"));
const About = lazy(() => import("./pages/About.jsx"));
const UsersPage = lazy(() => import("./pages/Users.jsx"));
const Approvals = lazy(() => import("./pages/Approvals.jsx"));
const Schools = lazy(() => import("./pages/Schools.jsx"));
const Account = lazy(() => import("./pages/Account.jsx"));

/** [path, label, icon, visible(auth) , group] */
const NAV = [
  ["/", "Dashboard", LayoutDashboard, (a) => !a.isStudent && !a.isSuper, "Overview"],
  ["/me", "My Profile", UserCircle, (a) => a.isStudent, "Overview"],
  ["/students", "Students", GraduationCap, (a) => !a.isSuper, "School"],
  ["/staff", "Staff", Users, (a) => !a.isSuper, "School"],
  ["/subjects", "Subjects", BookOpen, (a) => !a.isSuper, "School"],
  ["/fees", "Fees", Wallet, (a) => a.can("fees.view") || a.can("fees.manage"), "School"],
  ["/events", "Events", CalendarDays, (a) => !a.isSuper, "Campus"],
  ["/gallery", "Gallery", Images, (a) => !a.isSuper, "Campus"],
  ["/goals", "Future Goals", Target, (a) => !a.isSuper, "Campus"],
  ["/about", "About School", Info, (a) => !a.isSuper, "Campus"],
  ["/approvals", "Photo Approvals", Camera, (a) => a.can("photos.approve"), "Admin"],
  ["/users", "Users & Access", ShieldCheck, (a) => a.can("users.manage"), "Admin"],
  ["/schools", "Schools", Building2, (a) => a.isSuper, "Platform"],
  ["/account", "My Account", KeyRound, () => true, "Admin"],
];

function Shell() {
  const auth = useAuth();
  const { session, logout, isStudent, isSuper } = auth;
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(0);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    if (auth.can("photos.approve")) api("/photo-requests").then((r) => setPending(r.length)).catch(() => {});
  }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!session) return <Navigate to="/login" replace />;

  const items = NAV.filter((n) => n[3](auth));
  const groups = [...new Set(items.map((n) => n[4]))];
  return (
    <div className="layout">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="logo"><Logo size={22} /></span>
          <div>{isSuper ? "Platform Console" : session.school?.name}<small>School Management Suite</small></div>
        </div>
        <nav className="nav">
          {groups.map((g) => (
            <div key={g}>
              <div className="nav-group">{g}</div>
              {items.filter((n) => n[4] === g).map(([to, label, Icon]) => (
                <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
                  <Icon size={18} /> {label}
                  {to === "/approvals" && pending > 0 && <span className="count">{pending}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="me">
          <Photo kind="students" id={session.student_id} name={session.name} has={false} size={36} />
          <div className="who"><b>{session.name}</b><span>{session.role}</span></div>
          <button className="icon-btn" title="Sign out" onClick={logout} style={{ color: "#aeb7d6" }}><LogOut size={18} /></button>
        </div>
      </aside>
      <div className="content">
        <div className="topbar">
          <button className="icon-btn" onClick={() => setOpen((o) => !o)} aria-label="Menu"><Menu size={22} /></button>
          <b>{isSuper ? "Platform Console" : session.school?.name}</b>
        </div>
        <main className="main">
          <Suspense fallback={<div className="empty">Loading…</div>}><Outlet /></Suspense>
        </main>
      </div>
      {!isSuper && <Chatbot />}
    </div>
  );
}

function Guard({ ok, children }) {
  return ok ? children : <Navigate to="/" replace />;
}

export default function App() {
  const a = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Shell />}>
        <Route index element={a.isSuper ? <Navigate to="/schools" replace /> : a.isStudent ? <Navigate to="/me" replace /> : <Dashboard />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="me" element={<Guard ok={a.isStudent}><StudentDetail me /></Guard>} />
        <Route path="students" element={<Guard ok={!a.isSuper}><Students /></Guard>} />
        <Route path="students/:id" element={<Guard ok={!a.isSuper}><StudentDetail /></Guard>} />
        <Route path="fees" element={<Guard ok={a.can("fees.view") || a.can("fees.manage")}><Fees /></Guard>} />
        <Route path="subjects" element={<Guard ok={!a.isSuper}><Subjects /></Guard>} />
        <Route path="subjects/:id" element={<Guard ok={!a.isSuper}><SubjectDetail /></Guard>} />
        <Route path="staff" element={<Guard ok={!a.isSuper}><Staff /></Guard>} />
        <Route path="staff/:id" element={<Guard ok={!a.isSuper}><StaffDetail /></Guard>} />
        <Route path="events" element={<Guard ok={!a.isSuper}><Events /></Guard>} />
        <Route path="gallery" element={<Guard ok={!a.isSuper}><Gallery /></Guard>} />
        <Route path="goals" element={<Guard ok={!a.isSuper}><Goals /></Guard>} />
        <Route path="about" element={<Guard ok={!a.isSuper}><About /></Guard>} />
        <Route path="approvals" element={<Guard ok={a.can("photos.approve")}><Approvals /></Guard>} />
        <Route path="users" element={<Guard ok={a.can("users.manage")}><UsersPage /></Guard>} />
        <Route path="schools" element={<Guard ok={a.isSuper}><Schools /></Guard>} />
        <Route path="account" element={<Account />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
