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

async function parse(res) {
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!res.ok) {
    let msg = "Something went wrong";
    if (typeof data?.detail === "string") msg = data.detail;
    else if (Array.isArray(data?.detail)) msg = data.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ");
    throw new ApiError(res.status, msg);
  }
  return data;
}

function authHeaders(extra = {}) {
  const s = getSession();
  return s?.token ? { ...extra, Authorization: `Bearer ${s.token}` } : extra;
}

function expire(res) {
  if (res.status === 401 && getSession()) {
    setSession(null);
    window.location.assign("/login");
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: authHeaders(body !== undefined ? { "Content-Type": "application/json" } : {}),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  expire(res);
  if (res.status === 204) return null;
  return parse(res);
}

/** Upload raw image bytes (the API validates type and size). */
export async function upload(path, file) {
  const res = await fetch(`/api${path}`, { method: "POST", headers: authHeaders({ "Content-Type": "application/octet-stream" }), body: file });
  expire(res);
  if (res.status === 204) return null;
  return parse(res);
}

/** Fetch an authenticated image and return an object URL (images can't send auth headers via <img>). */
export async function fetchImage(path) {
  const res = await fetch(`/api${path}`, { headers: authHeaders() });
  if (!res.ok) return null;
  return URL.createObjectURL(await res.blob());
}

export const inr = (n) => (n == null ? "–" : `₹${Math.round(n).toLocaleString("en-IN")}`);
export const gradeLabel = (g) => (g === "LKG" || g === "UKG" ? g : `Class ${g}`);
export const GRADES = ["LKG", "UKG", ...Array.from({ length: 10 }, (_, i) => String(i + 1))];
