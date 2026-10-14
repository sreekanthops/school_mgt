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
  return (
    <Ctx.Provider value={{ session, isAdmin: session?.role === "admin", login, logout }}>
      {children}
    </Ctx.Provider>
  );
}
