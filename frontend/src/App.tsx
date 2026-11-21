import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./authContext";
import RequirePermission from "./components/RequirePermission";
import Shell from "./components/Shell";
import AuditLog from "./pages/AuditLog";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Roles from "./pages/Roles";
import Users from "./pages/Users";
import Workspace from "./pages/Workspace";

// Pages that need a login. Anonymous visitors are sent to /login.
function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") return <p className="muted center">Loading…</p>;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  return children;
}

// Login and sign-up pages. Someone already logged in is sent to the workspace.
function PublicOnly({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === "loading") return <p className="muted center">Loading…</p>;
  if (status === "authenticated") return <Navigate to="/workspace" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/workspace" replace />} />
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
      <Route element={<RequireAuth><Shell /></RequireAuth>}>
        <Route path="/workspace" element={<Workspace />} />
        <Route path="/users" element={<RequirePermission permission="users.view"><Users /></RequirePermission>} />
        <Route path="/roles" element={<RequirePermission permission="roles.view"><Roles /></RequirePermission>} />
        <Route path="/audit" element={<RequirePermission permission="audit.view"><AuditLog /></RequirePermission>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
