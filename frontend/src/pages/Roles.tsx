import { useCallback, useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { useAuth } from "../authContext";

function errorText(e: unknown): string {
  return e instanceof api.ApiError ? e.message : "Something went wrong";
}

export default function Roles() {
  const { can } = useAuth();
  const canManage = can("roles.manage");
  const [roles, setRoles] = useState<api.Role[]>([]);
  const [catalogue, setCatalogue] = useState<api.Permission[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<api.Role | "new" | null>(null);

  const reload = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([api.listRoles(), api.listPermissions()]);
      setRoles(r);
      setCatalogue(p);
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading data on mount
    void reload();
  }, [reload]);

  async function handleDelete(role: api.Role) {
    if (!window.confirm(`Delete role "${role.name}"? Users holding it will lose it.`)) return;
    try {
      await api.deleteRole(role.id);
      await reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <section>
      <div className="toolbar">
        <h2>Roles</h2>
        {canManage && editing === null && <button onClick={() => setEditing("new")}>New role</button>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      {editing !== null && (
        <RoleForm
          role={editing === "new" ? null : editing}
          catalogue={catalogue}
          onDone={async () => {
            setEditing(null);
            await reload();
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      <ul className="list">
        {roles.map((role) => (
          <li key={role.id}>
            <div className="row">
              <div>
                <strong>{role.name}</strong>
                {role.is_system && <span className="badge">system</span>}
                {role.description && <p className="muted">{role.description}</p>}
              </div>
              {canManage && !role.is_system && (
                <div className="actions">
                  <button className="secondary" onClick={() => setEditing(role)}>Edit</button>
                  <button className="secondary" onClick={() => handleDelete(role)}>Delete</button>
                </div>
              )}
            </div>
            <p className="chips">
              {role.permissions.length === 0 && <span className="muted">No permissions</span>}
              {role.permissions.map((p) => (
                <span key={p.key} className="chip" title={p.description}>{p.key}</span>
              ))}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RoleForm({
  role,
  catalogue,
  onDone,
  onCancel,
}: {
  role: api.Role | null;
  catalogue: api.Permission[];
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const { can } = useAuth();
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected, setSelected] = useState<Set<string>>(
    new Set(role?.permissions.map((p) => p.key) ?? []),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function toggle(key: string) {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setSelected(next);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    const input = { name, description, permission_keys: [...selected] };
    try {
      if (role) await api.updateRole(role.id, input);
      else await api.createRole(input);
      await onDone();
    } catch (e) {
      setError(errorText(e));
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <h2>{role ? `Edit ${role.name}` : "New role"}</h2>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} />
      </label>
      <label>
        Description
        <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={255} />
      </label>
      <fieldset>
        <legend>Permissions</legend>
        {catalogue.map((p) => {
          // You can only grant what you hold. The backend enforces it; greying out here
          // just saves a round trip. Permissions already on the role stay enabled so the
          // role can be saved unchanged.
          const held = can(p.key) || (role?.permissions.some((x) => x.key === p.key) ?? false);
          return (
            <label key={p.key} className="check">
              <input
                type="checkbox"
                checked={selected.has(p.key)}
                disabled={!held}
                onChange={() => toggle(p.key)}
              />
              <span>
                <code>{p.key}</code> <span className="muted">{p.description}</span>
              </span>
            </label>
          );
        })}
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
