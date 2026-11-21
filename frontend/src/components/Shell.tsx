import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../authContext";

// Every logged-in page lives inside this frame: header, navigation, logout.
export default function Shell() {
  const { me, signOut, can } = useAuth();
  const navigate = useNavigate();
  if (!me) return null;

  function handleLogout() {
    signOut();
    navigate("/login");
  }

  // Menu entries appear only for people who may use them. This is convenience:
  // the pages and the backend check permissions again.
  const links = [
    { to: "/workspace", label: "Workspace", show: true },
    { to: "/users", label: "Users", show: can("users.view") },
    { to: "/roles", label: "Roles", show: can("roles.view") },
    { to: "/audit", label: "Audit log", show: can("audit.view") },
  ].filter((l) => l.show);

  return (
    <div className="workspace">
      <header>
        <div>
          <h1>{me.organization.name}</h1>
          <p className="muted">
            {me.user.full_name} ({me.user.email}) · {me.user.roles.map((r) => r.name).join(", ") || "no roles"}
          </p>
        </div>
        <button className="secondary" onClick={handleLogout}>
          Log out
        </button>
      </header>
      <nav>
        {links.map((l) => (
          <NavLink key={l.to} to={l.to}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
