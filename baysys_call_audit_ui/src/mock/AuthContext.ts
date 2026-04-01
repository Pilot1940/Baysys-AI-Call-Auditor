import { createContext } from "react";
import type { AuthUser } from "../types/audit";

export interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
}

export const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
});
