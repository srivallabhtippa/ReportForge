import { useNavigate } from "react-router-dom";
import { useAuth } from "../authContext";

export default function Workspace() {
  const { me, signOut } = useAuth();
  const navigate = useNavigate();

  // The route guard in App.tsx guarantees we are logged in, but TypeScript
  // cannot know that, so handle the "no data" case.
  if (!me) return null;

  function handleLogout() {
    signOut();
    navigate("/login");
  }

  return (
    <main className="workspace">
      <header>
        <div>
          <h1>{me.organization.name}</h1>
          <p className="muted">
            Signed in as {me.user.full_name} ({me.user.email}) · role: {me.user.role}
          </p>
        </div>
        <button className="secondary" onClick={handleLogout}>
          Log out
        </button>
      </header>
      <section className="empty">
        <h2>Your workspace is ready</h2>
        <p className="muted">
          Nothing here yet. Roles and users arrive in the next release, then datasets
          and reports.
        </p>
      </section>
    </main>
  );
}
