import { lazy, Suspense } from "react";
import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Chatbot from "./components/Chatbot.jsx";
import Login from "./pages/Login.jsx";
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
import Students from "./pages/Students.jsx";
const StudentDetail = lazy(() => import("./pages/StudentDetail.jsx"));
import Subjects from "./pages/Subjects.jsx";
import Staff from "./pages/Staff.jsx";
import EventsGallery from "./pages/EventsGallery.jsx";
import About from "./pages/About.jsx";
import Goals from "./pages/Goals.jsx";

const NAV = [
  ["/", "Dashboard"], ["/students", "Students"], ["/subjects", "Subjects"], ["/staff", "Staff"],
  ["/events", "Events & Gallery"], ["/goals", "Future Goals"], ["/about", "About"],
];

function Shell() {
  const { session, logout } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">Sunrise Public School<small>Management Suite</small></div>
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
          ))}
        </nav>
        <div className="user">
          {session.name} <span className="badge">{session.role}</span>
          <div><a href="#logout" onClick={(e) => { e.preventDefault(); logout(); }}>Sign out</a></div>
        </div>
      </aside>
      <main className="main"><Suspense fallback={<div className="empty">Loading…</div>}><Outlet /></Suspense></main>
      <Chatbot />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="students" element={<Students />} />
        <Route path="students/:id" element={<StudentDetail />} />
        <Route path="subjects" element={<Subjects />} />
        <Route path="staff" element={<Staff />} />
        <Route path="events" element={<EventsGallery />} />
        <Route path="goals" element={<Goals />} />
        <Route path="about" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
