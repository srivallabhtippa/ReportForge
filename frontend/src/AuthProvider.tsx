import { useEffect, useState, type ReactNode } from "react";
import * as api from "./api";
import { AuthContext, type AuthState, type AuthStatus } from "./authContext";

export default function AuthProvider({ children }: { children: ReactNode }) {
  // If a token is saved, we do not know yet whether it is still valid, so start in
  // "loading" and ask the backend. Otherwise we are certainly logged out.
  const [status, setStatus] = useState<AuthStatus>(() =>
    api.getToken() ? "loading" : "anonymous",
  );
  const [me, setMe] = useState<api.Me | null>(null);

  // On first load (and after a refresh): is the saved token still good?
  useEffect(() => {
    if (!api.getToken()) return;
    api
      .getMe()
      .then((data) => {
        setMe(data);
        setStatus("authenticated");
      })
      .catch(() => {
        api.clearToken(); // expired, forged or user disabled: forget it
        setStatus("anonymous");
      });
  }, []);

  const signIn: AuthState["signIn"] = async (email, password) => {
    await api.login(email, password);
    setMe(await api.getMe());
    setStatus("authenticated");
  };

  const signUp: AuthState["signUp"] = async (input) => {
    await api.register(input);
    await signIn(input.email, input.password); // registering also logs you in
  };

  const signOut = () => {
    api.clearToken();
    setMe(null);
    setStatus("anonymous");
  };

  return (
    <AuthContext.Provider value={{ status, me, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
