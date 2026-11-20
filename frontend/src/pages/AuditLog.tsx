import { useEffect, useState } from "react";
import * as api from "../api";

const PAGE_SIZE = 25;

const ACTIONS = [
  "organization.registered",
  "auth.login",
  "role.created",
  "role.updated",
  "role.deleted",
  "user.created",
  "user.updated",
  "user.disabled",
  "user.enabled",
  "user.roles_changed",
];

export default function AuditLog() {
  const [events, setEvents] = useState<api.AuditEvent[]>([]);
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false; // ignore a slow answer that arrives after the filter changed
    api
      .listAuditLog({ action: action || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((data) => {
        if (cancelled) return;
        setEvents(data);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof api.ApiError ? e.message : "Something went wrong");
      });
    return () => {
      cancelled = true;
    };
  }, [action, page]);

  return (
    <section>
      <div className="toolbar">
        <h2>Audit log</h2>
        <label className="inline">
          Action
          <select
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(0);
            }}
          >
            <option value="">All</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <table>
        <thead>
          <tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td>{new Date(e.created_at).toLocaleString()}</td>
              <td>{e.actor_email ?? <span className="muted">unknown</span>}</td>
              <td><code>{e.action}</code></td>
              <td><code className="details">{JSON.stringify(e.details)}</code></td>
            </tr>
          ))}
          {events.length === 0 && (
            <tr><td colSpan={4} className="muted">No events.</td></tr>
          )}
        </tbody>
      </table>
      <div className="actions">
        <button className="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</button>
        <button className="secondary" disabled={events.length < PAGE_SIZE} onClick={() => setPage(page + 1)}>Older</button>
      </div>
    </section>
  );
}
