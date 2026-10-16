import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import {
  AlertTriangle, BookOpen, Building2, CalendarCheck, CalendarClock, CalendarRange, ClipboardList, FileUp, Megaphone, Receipt, Lightbulb, CalendarDays, GraduationCap, Images, Info, KeyRound, LayoutDashboard, LogOut, Menu,
  MessagesSquare, ShieldCheck, Target, UserCircle, Users, Wallet, Camera, GraduationCap as Logo,
} from "lucide-react";
import { api } from "./api.js";
import { useAuth } from "./auth.jsx";
import Chatbot from "./components/Chatbot.jsx";
import { Photo } from "./components/ui.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import Login from "./pages/Login.jsx";
import ResetOwnerPassword from "./pages/ResetOwnerPassword.jsx";

const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const StaffHome = lazy(() => import("./pages/StaffHome.jsx"));
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
const SchoolDetail = lazy(() => import("./pages/SchoolDetail.jsx"));
const Account = lazy(() => import("./pages/Account.jsx"));
const Messages = lazy(() => import("./pages/Messages.jsx"));
const Board = lazy(() => import("./pages/Board.jsx"));
const Announcements = lazy(() => import("./pages/Announcements.jsx"));
const Attendance = lazy(() => import("./pages/Attendance.jsx"));
const Classes = lazy(() => import("./pages/Classes.jsx"));
const NewYear = lazy(() => import("./pages/NewYear.jsx"));
const SmartImport = lazy(() => import("./pages/SmartImport.jsx"));
const Holidays = lazy(() => import("./pages/Holidays.jsx"));
const Leaves = lazy(() => import("./pages/Leaves.jsx"));
const MyBilling = lazy(() => import("./components/Billing.jsx").then((m) => ({ default: m.MyBilling })));

/** [path, label, icon, visible(auth) , group] */
const NAV = [
  ["/", "Dashboard", LayoutDashboard, (a) => !a.isStudent && !a.isSuper && a.role !== "staff", "Overview"],
  ["/", "My Dashboard", LayoutDashboard, (a) => a.role === "staff", "Overview"],
  ["/me", "My Profile", UserCircle, (a) => a.isStudent, "Overview"],
  ["/students", "Students", GraduationCap, (a) => !a.isSuper, "School"],
  ["/staff", "Staff", Users, (a) => !a.isSuper, "School"],
  ["/subjects", "Subjects", BookOpen, (a) => !a.isSuper, "School"],
  ["/classes", "Timetable", CalendarClock, (a) => !a.isSuper && !a.isStudent, "School"],
  ["/attendance", "Attendance", CalendarCheck, (a) => a.can("attendance.manage") || a.can("students.view"), "School"],
  ["/fees", "Fees", Wallet, (a) => a.can("fees.view") || a.can("fees.manage"), "School"],
  ["/announcements", "Announcements", Megaphone, (a) => !a.isSuper, "Campus"],
  ["/messages", "Messages", MessagesSquare, (a) => !a.isSuper, "Campus"],
  ["/board", "Idea Board", Lightbulb, (a) => !a.isSuper, "Campus"],
  ["/events", "Events", CalendarDays, (a) => !a.isSuper, "Campus"],
  ["/gallery", "Gallery", Images, (a) => !a.isSuper, "Campus"],
  ["/goals", "Future Goals", Target, (a) => !a.isSuper, "Campus"],
  ["/holidays", "Holidays", CalendarRange, (a) => !a.isSuper, "Campus"],
  ["/about", "About School", Info, (a) => !a.isSuper, "Campus"],
  ["/leaves", "Staff Leaves", ClipboardList, (a) => !a.isSuper && !a.isStudent, "Admin"],
  ["/import", "Smart Import", FileUp, (a) => a.can("students.manage") || a.can("staff.manage") || a.can("fees.manage") || a.can("subjects.manage") || a.can("content.manage") || a.can("marks.edit"), "Admin"],
  ["/approvals", "Photo Approvals", Camera, (a) => a.can("photos.approve"), "Admin"],
  ["/users", "Users & Access", ShieldCheck, (a) => a.can("users.manage"), "Admin"],
  ["/billing", "Billing", Receipt, (a) => a.role === "admin", "Admin"],
  ["/schools", "Schools", Building2, (a) => a.isSuper, "Platform"],
  ["/account", "My Account", KeyRound, () => true, "Admin"],
];

/** Pages that stay fully usable after the subscription ends (messaging and own password). */
const KEEP_OPEN = ["/messages", "/account"];

function SubscriptionBanner({ sub }) {
  if (!sub || (!sub.locked && !sub.reminder)) return null;
  const date = sub.end;
  const text = sub.locked
    ? `Subscription expired on ${date}. The school is read-only: you can sign in and view everything, but adding or changing data is switched off. Contact the platform team to renew.`
    : `Reminder ${sub.reminder} of 3: your subscription ends on ${date} (${sub.days_left === 0 ? "today" : `${sub.days_left} day${sub.days_left === 1 ? "" : "s"} left`}). After that the school becomes read-only. Contact the platform team to renew.`;
  return (
    <div className={`sub-banner ${sub.locked || sub.reminder === 3 ? "bad" : "warn"}`} role="alert">
      <AlertTriangle size={18} /> <span>{text}</span>
    </div>
  );
}

function Shell() {
  const auth = useAuth();
  const { session, logout, isStudent, isSuper } = auth;
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(0);
  const [unread, setUnread] = useState(0);
  const [notices, setNotices] = useState(0);
  const [setupPrompt, setSetupPrompt] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => setSetupPrompt(false), [loc.pathname]);
  // pick up a renewal (or a new reminder stage) without needing to sign out and in
  useEffect(() => {
    if (session && !isSuper && !isStudent) auth.refresh().catch(() => {});
  }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (auth.can("photos.approve")) api("/photo-requests").then((r) => setPending(r.length)).catch(() => {});
  }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!session || isSuper) return undefined;
    const load = () => {
      api("/messages/unread").then((r) => setUnread(r.count)).catch(() => {});
      api("/announcements/unread").then((r) => setNotices(r.count)).catch(() => {});
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [session, isSuper, loc.pathname]);
  if (!session) return <Navigate to="/login" replace />;
  if (session.must_change && loc.pathname !== "/account") return <Navigate to="/account" replace />;
  if (session.must_setup_recovery && loc.pathname !== "/account") return <Navigate to="/account" replace />;

  const setupPending = !!(session.must_change || session.must_setup_recovery);

  const locked = !!session.subscription?.locked;
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
          {setupPending && (
            <div className="setup-nav-notice">
              <span>⚠ Complete account setup to unlock all menus</span>
            </div>
          )}
          {groups.map((g) => (
            <div key={g}>
              <div className="nav-group">{g}</div>
              {items.filter((n) => n[4] === g).map(([to, label, Icon]) => {
                const isAccount = to === "/account";
                const blocked = setupPending && !isAccount;
                return blocked ? (
                  <button key={to} className="nav-blocked" onClick={() => setSetupPrompt(true)}
                    title="Complete account setup first">
                    <Icon size={18} /> {label}
                  </button>
                ) : (
                  <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
                    <Icon size={18} /> {label}
                    {to === "/approvals" && pending > 0 && <span className="count">{pending}</span>}
                    {to === "/messages" && unread > 0 && <span className="count">{unread}</span>}
                    {to === "/announcements" && notices > 0 && loc.pathname !== "/announcements" && <span className="count">{notices}</span>}
                  </NavLink>
                );
              })}
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
        <SubscriptionBanner sub={session.subscription} />
        {setupPrompt && (
          <div className="setup-banner" role="alert">
            <span>
              {session.must_change
                ? "⚠ You must change your temporary password before you can use the system."
                : "⚠ You must set up your password recovery questions before you can use the system."}
              {" "}Go to <a href="/account" style={{ color: "inherit", fontWeight: 700, textDecoration: "underline" }}>My Account</a> to complete setup.
            </span>
            <button onClick={() => setSetupPrompt(false)} style={{ background: "none", border: 0, color: "inherit", cursor: "pointer", fontWeight: 700, fontSize: 16, padding: "0 4px" }}>✕</button>
          </div>
        )}
        <main className={`main ${locked && !KEEP_OPEN.some((p) => loc.pathname.startsWith(p)) ? "locked" : ""}`}>
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
      <Route path="/forgot" element={<ForgotPassword />} />
      <Route path="/reset-owner-password" element={<ResetOwnerPassword />} />
      <Route element={<Shell />}>
        <Route index element={
          a.isSuper ? <Navigate to="/schools" replace />
          : a.isStudent ? <Navigate to="/me" replace />
          : a.role === "staff" ? <StaffHome />
          : <Dashboard />
        } />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="me" element={<Guard ok={a.isStudent}><StudentDetail me /></Guard>} />
        <Route path="students" element={<Guard ok={!a.isSuper}><Students /></Guard>} />
        <Route path="students/:id" element={<Guard ok={!a.isSuper}><StudentDetail /></Guard>} />
        <Route path="fees" element={<Guard ok={a.can("fees.view") || a.can("fees.manage")}><Fees /></Guard>} />
        <Route path="subjects" element={<Guard ok={!a.isSuper}><Subjects /></Guard>} />
        <Route path="subjects/:id" element={<Guard ok={!a.isSuper}><SubjectDetail /></Guard>} />
        <Route path="staff" element={<Guard ok={!a.isSuper}><Staff /></Guard>} />
        <Route path="staff/:id" element={<Guard ok={!a.isSuper}><StaffDetail /></Guard>} />
        <Route path="messages" element={<Guard ok={!a.isSuper}><Messages /></Guard>} />
        <Route path="announcements" element={<Guard ok={!a.isSuper}><Announcements /></Guard>} />
        <Route path="attendance" element={<Guard ok={a.can("attendance.manage") || a.can("students.view")}><Attendance /></Guard>} />
        <Route path="classes" element={<Guard ok={!a.isSuper && !a.isStudent}><Classes /></Guard>} />
        <Route path="new-year" element={<Guard ok={a.can("school.manage") && a.can("students.manage")}><NewYear /></Guard>} />
        <Route path="import" element={<Guard ok={a.can("students.manage") || a.can("staff.manage") || a.can("fees.manage") || a.can("subjects.manage") || a.can("content.manage") || a.can("marks.edit")}><SmartImport /></Guard>} />
        <Route path="billing" element={<Guard ok={a.role === "admin"}><MyBilling /></Guard>} />
        <Route path="board" element={<Guard ok={!a.isSuper}><Board /></Guard>} />
        <Route path="events" element={<Guard ok={!a.isSuper}><Events /></Guard>} />
        <Route path="gallery" element={<Guard ok={!a.isSuper}><Gallery /></Guard>} />
        <Route path="goals" element={<Guard ok={!a.isSuper}><Goals /></Guard>} />
        <Route path="about" element={<Guard ok={!a.isSuper}><About /></Guard>} />
        <Route path="approvals" element={<Guard ok={a.can("photos.approve")}><Approvals /></Guard>} />
        <Route path="holidays" element={<Guard ok={!a.isSuper}><Holidays /></Guard>} />
        <Route path="leaves" element={<Guard ok={!a.isSuper && !a.isStudent}><Leaves /></Guard>} />
        <Route path="users" element={<Guard ok={a.can("users.manage")}><UsersPage /></Guard>} />
        <Route path="schools" element={<Guard ok={a.isSuper}><Schools /></Guard>} />
        <Route path="schools/:id" element={<Guard ok={a.isSuper}><SchoolDetail /></Guard>} />
        <Route path="account" element={<Account />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
