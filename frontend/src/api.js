const KEY = "school_session";

export function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY)) || null;
  } catch {
    return null;
  }
}
export function setSession(s) {
  if (s) sessionStorage.setItem(KEY, JSON.stringify(s));
  else sessionStorage.removeItem(KEY);
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const s = getSession();
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (s?.token) headers.Authorization = `Bearer ${s.token}`;
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && s) {
    setSession(null);
    window.location.assign("/login");
  }
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    let msg = "Something went wrong";
    if (typeof data?.detail === "string") msg = data.detail;
    else if (Array.isArray(data?.detail)) msg = data.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ");
    throw new ApiError(res.status, msg);
  }
  return data;
}

export const inr = (n) => `₹${Math.round(n ?? 0).toLocaleString("en-IN")}`;
export const gradeLabel = (g) => (g === "LKG" || g === "UKG" ? g : `Class ${g}`);
