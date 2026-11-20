import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { useAuth } from "../authContext";

function errorText(e: unknown): string {
  return e instanceof api.ApiError ? e.message : "Something went wrong";
}

export default function Users() {
  const { can, me } = useAuth();
  const canManage = can("users.manage");
  const [users, setUsers] = useState<api.User[]>([]);
  // Role names are needed to assign roles; that needs roles.view.
  const [roles, setRoles] = useState<api.Role[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<api.User | "new" | null>(null);
  const canListRoles = can("roles.view");

  const reload = useCallback(async () => {
    try {
      setUsers(await api.listUsers());
      if (canListRoles) setRoles(await api.listRoles());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [canListRoles]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading data on mount
    void reload();
  }, [reload]);

  async function toggleActive(user: api.User) {
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      await reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <section>
      <div className="toolbar">
        <h2>Users</h2>
        {canManage && editing === null && <button onClick={() => setEditing("new")}>New user</button>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      {editing !== null && (
        <UserForm
          user={editing === "new" ? null : editing}
          roles={roles}
          canAssignRoles={canListRoles}
          onDone={async () => {
            setEditing(null);
            await reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      <table>
        <thead>
          <tr><th>Name</th><th>Email</th><th>Roles</th><th>Status</th>{canManage && <th />}</tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.full_name}</td>
              <td>{u.email}</td>
              <td>{u.roles.map((r) => r.name).join(", ") || <span className="muted">none</span>}</td>
              <td>{u.is_active ? "Active" : <span className="badge off">Disabled</span>}</td>
              {canManage && (
                <td className="actions">
                  <button className="secondary" onClick={() => setEditing(u)}>Edit</button>
                  <button className="secondary" onClick={() => toggleActive(u)}>
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {me && <p className="muted">Changes appear in the audit log.</p>}
    </section>
  );
}

function UserForm({
  user,
  roles,
  canAssignRoles,
  onDone,
  onCancel,
}: {
  user: api.User | null;
  roles: api.Role[];
  canAssignRoles: boolean;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const { can } = useAuth();
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set(user?.roles.map((r) => r.id) ?? []));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      if (user) {
        await api.updateUser(user.id, {
          full_name: fullName,
          ...(canAssignRoles ? { role_ids: [...selected] } : {}),
        });
      } else {
        await api.createUser({ email, full_name: fullName, password, role_ids: [...selected] });
      }
      await onDone();
    } catch (e) {
      setError(errorText(e));
      setSaving(false);
    }
  }

  // A role can be given only if you hold all of its permissions (the backend enforces it).
  const grantable = (r: api.Role) =>
    r.permissions.every((p) => can(p.key)) || (user?.roles.some((x) => x.id === r.id) ?? false);

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <h2>{user ? `Edit ${user.full_name}` : "New user"}</h2>
      {!user && (
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
      )}
      <label>
        Full name
        <input value={fullName} onChange={(e) => setFullName(e.target.value)} required minLength={2} />
      </label>
      {!user && (
        <label>
          Initial password (at least 12 characters)
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={12}
          />
        </label>
      )}
      {canAssignRoles && (
        <fieldset>
          <legend>Roles</legend>
          {roles.map((r) => (
            <label key={r.id} className="check">
              <input
                type="checkbox"
                checked={selected.has(r.id)}
                disabled={!grantable(r)}
                onChange={() => toggle(r.id)}
              />
              <span>{r.name}</span>
            </label>
          ))}
        </fieldset>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
