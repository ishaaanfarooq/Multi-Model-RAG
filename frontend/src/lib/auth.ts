// Client-side session for the Praxis API: one JWT access token, kept in localStorage.
//
// The token travels as `Authorization: Bearer` on fetch, and as an `access_token` query parameter
// only on EventSource URLs, because EventSource cannot send headers. Cookies are not used: the
// components disagree on the API host (127.0.0.1 vs localhost), and a cookie set for one host is
// never sent to the other. Everything here is safe to import on the server (typeof window guards).

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type AuthUser = { id: string; name: string; email: string; created_at: string };
export type Session = { token: string; user: AuthUser; exp: number }; // exp = JWT exp (unix seconds)

export class AuthError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "AuthError";
    this.status = status;
  }
}

const STORAGE_KEY = "mmrag.auth.v1";
const AUTH_EVENT = "mmrag:auth";

type AuthResponse = { access_token: string; token_type: string; expires_in: number; user: AuthUser };

// ── token + storage ──────────────────────────────────────────────────────────

/** The `exp` claim (unix seconds) from a JWT payload, without verifying it: the server does that. */
function tokenExp(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const claims: unknown = JSON.parse(atob(padded));
    const exp = (claims as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

function isSession(value: unknown): value is Session {
  const v = value as Partial<Session> | null;
  return (
    !!v &&
    typeof v.token === "string" &&
    typeof v.exp === "number" &&
    !!v.user &&
    typeof v.user.id === "string" &&
    typeof v.user.name === "string" &&
    typeof v.user.email === "string"
  );
}

function notify() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EVENT));
}

function removeStored() {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** The stored session, or null when it is missing, malformed or expired (an expired one is cleared). */
export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isSession(parsed)) return null;
  if (parsed.exp * 1000 <= Date.now()) {
    removeStored();
    return null;
  }
  return parsed;
}

function saveSession(data: AuthResponse): Session {
  const exp = tokenExp(data.access_token) ?? Math.floor(Date.now() / 1000) + data.expires_in;
  const session: Session = { token: data.access_token, user: data.user, exp };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* ignore: the session still works for this page */
  }
  notify();
  return session;
}

/** `{ Authorization: "Bearer …" }`, or `{}` when signed out, so call sites need no branching. */
export function authHeaders(): Record<string, string> {
  const session = getSession();
  return session ? { Authorization: `Bearer ${session.token}` } : {};
}

/** Appends `access_token` for EventSource URLs; returns the URL unchanged when signed out. */
export function withToken(url: string): string {
  const session = getSession();
  if (!session) return url;
  return `${url}${url.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(session.token)}`;
}

// ── API calls ────────────────────────────────────────────────────────────────

function errorMessage(status: number, data: unknown): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (status === 422 && Array.isArray(detail) && detail.length > 0) {
    const msg = (detail[0] as { msg?: unknown }).msg;
    if (typeof msg === "string") return msg.replace(/^Value error, /, "");
  }
  if (typeof detail === "string" && detail && status !== 404) return detail; // 401, 409, 429, …
  if (status === 404) return "This backend has no sign-in endpoints. Restart it so it loads the latest code.";
  if (status >= 500) return `The Praxis backend hit an error (${status}). Check its console for details.`;
  return `Request failed (${status}).`;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new AuthError(0, `Can't reach the Praxis backend at ${API_BASE}. Is it running on port 8000?`);
  }
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) throw new AuthError(res.status, errorMessage(res.status, data));
  return data as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function login(email: string, password: string): Promise<Session> {
  return saveSession(await request<AuthResponse>("/api/auth/login", json({ email, password })));
}

export async function register(name: string, email: string, password: string): Promise<Session> {
  return saveSession(await request<AuthResponse>("/api/auth/register", json({ name, email, password })));
}

/** The signed-in user according to the server. Throws AuthError (status 0 = network failure). */
export async function fetchMe(): Promise<AuthUser> {
  const data = await request<{ user: AuthUser }>("/api/auth/me", { headers: authHeaders() });
  return data.user;
}

export function logout(): void {
  if (typeof window === "undefined") return;
  removeStored();
  notify();
}

/** Calls `cb` on sign-in/out in this tab ("mmrag:auth") and in other tabs ("storage"). */
export function onAuthChange(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key === STORAGE_KEY) cb();
  };
  window.addEventListener(AUTH_EVENT, cb);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(AUTH_EVENT, cb);
    window.removeEventListener("storage", onStorage);
  };
}

/** A post-sign-in destination that cannot leave the site: a relative path, else "/". */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  // Browsers drop tabs/newlines and treat "\" as "/" in URLs, so "/\t/evil.com" would become "//evil.com".
  if (/[\u0000-\u001f\\]/.test(next)) return "/";
  return next;
}
