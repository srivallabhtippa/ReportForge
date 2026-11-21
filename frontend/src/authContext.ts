import { createContext, useContext } from "react";
import type { Me, RegisterInput } from "./api";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthState {
  status: AuthStatus;
  me: Me | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (input: RegisterInput) => Promise<void>;
  signOut: () => void;
  // True if the logged-in user holds the permission. For showing or hiding UI only:
  // the backend decides what is really allowed.
  can: (permission: string) => boolean;
}

export const AuthContext = createContext<AuthState | null>(null);

// Pages call useAuth() to read who is logged in and to log in or out.
export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
