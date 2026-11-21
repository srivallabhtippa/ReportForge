import type { ReactNode } from "react";
import { useAuth } from "../authContext";

// Guards a page. Typing the URL by hand does not help someone without the permission,
// and even if they got past this, every API call would still answer 403.
export default function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}) {
  const { can } = useAuth();
  if (!can(permission)) {
    return (
      <section className="empty">
        <h2>Not allowed</h2>
        <p className="muted">Your roles do not include access to this page.</p>
      </section>
    );
  }
  return children;
}
