// The only file that talks to the backend. Pages call these functions and never
// use fetch directly, so URLs, headers and error handling live in one place.

export interface Organization {
  id: string;
  name: string;
}

export interface RoleRef {
  id: string;
  name: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: RoleRef[];
}

export interface Me {
  organization: Organization;
  user: User;
  permissions: string[]; // what this user may do; used to hide UI, never to enforce
}

export interface Permission {
  key: string;
  description: string;
}

export interface Role {
  id: string;
  name: string;
  description: string;
  is_system: boolean;
  permissions: Permission[];
}

export interface AuditEvent {
  id: string;
  created_at: string;
  action: string;
  actor_email: string | null;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// --- Token storage -------------------------------------------------------------
// v1 keeps the token in localStorage: simple, and it survives a page refresh.
// Trade-off: any script running on the page (an XSS bug) can read it. The v4
// hardening release will revisit this (httpOnly cookie).
const TOKEN_KEY = "reportforge_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // storage can be blocked (private mode); behave as logged out
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // ignore: user will have to log in again after a refresh
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

// --- Errors --------------------------------------------------------------------
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// The backend sends {"detail": "text"} for our own errors and
// {"detail": [{loc, msg}, ...]} for validation errors. Turn both into one string.
function readableDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : "";
        return field ? `${field}: ${d.msg}` : String(d.msg);
      })
      .join(". ");
  }
  return "Something went wrong";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (!response.ok) {
    let message = "Something went wrong";
    try {
      message = readableDetail((await response.json()).detail);
    } catch {
      // body was not JSON; keep the generic message
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T; // DELETE answers with no body
  return response.json() as Promise<T>;
}

// --- Endpoints -----------------------------------------------------------------
export interface RegisterInput {
  organization_name: string;
  full_name: string;
  email: string;
  password: string;
}

export function register(input: RegisterInput): Promise<Me> {
  return request<Me>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function login(email: string, password: string): Promise<void> {
  const data = await request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.access_token);
}

export function getMe(): Promise<Me> {
  return request<Me>("/api/me");
}

// --- Roles ---------------------------------------------------------------------
export const listPermissions = () => request<Permission[]>("/api/permissions");
export const listRoles = () => request<Role[]>("/api/roles");

export interface RoleInput {
  name: string;
  description: string;
  permission_keys: string[];
}

export const createRole = (input: RoleInput) =>
  request<Role>("/api/roles", { method: "POST", body: JSON.stringify(input) });

export const updateRole = (id: string, input: Partial<RoleInput>) =>
  request<Role>(`/api/roles/${id}`, { method: "PATCH", body: JSON.stringify(input) });

export const deleteRole = (id: string) =>
  request<void>(`/api/roles/${id}`, { method: "DELETE" });

// --- Users ---------------------------------------------------------------------
export const listUsers = () => request<User[]>("/api/users");

export interface UserInput {
  email: string;
  full_name: string;
  password: string;
  role_ids: string[];
}

export const createUser = (input: UserInput) =>
  request<User>("/api/users", { method: "POST", body: JSON.stringify(input) });

export const updateUser = (
  id: string,
  input: { full_name?: string; is_active?: boolean; role_ids?: string[] },
) => request<User>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(input) });

// --- Audit log -----------------------------------------------------------------
export const listAuditLog = (params: { action?: string; limit: number; offset: number }) => {
  const query = new URLSearchParams({
    limit: String(params.limit),
    offset: String(params.offset),
  });
  if (params.action) query.set("action", params.action);
  return request<AuditEvent[]>(`/api/audit-log?${query}`);
};
