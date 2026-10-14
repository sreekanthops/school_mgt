import { createContext, useContext, useState } from "react";
import { api, getSession, setSession } from "./api.js";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [session, setS] = useState(getSession());

  async function login(username, password) {
    const r = await api("/auth/login", { method: "POST", body: { username, password } });
    setSession(r);
    setS(r);
  }
  function logout() {
    setSession(null);
    setS(null);
  }
  async function refresh() {
    const me = await api("/auth/me");
    const next = { ...session, ...me };
    setSession(next);
    setS(next);
  }
  const perms = new Set(session?.permissions ?? []);
  const value = {
    session,
    role: session?.role,
    isSuper: session?.role === "superadmin",
    isStudent: session?.role === "student",
    can: (p) => perms.has(p),
    login,
    logout,
    refresh,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
