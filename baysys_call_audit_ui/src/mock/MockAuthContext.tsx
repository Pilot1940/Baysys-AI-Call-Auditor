import { type ReactNode } from "react";
import { AuthContext } from "./AuthContext";
import type { AuthUser } from "../types/audit";

const MOCK_USER: AuthUser = {
  user_id: 1,
  role_id: 2,
  agency_id: 1,
  first_name: "BaySys.AI",
  last_name: "Test User",
  email: "connect@baysys.ai",
};

export function MockAuthProvider({ children }: { children: ReactNode }) {
  return (
    <AuthContext.Provider value={{ user: MOCK_USER, isAuthenticated: true }}>
      {children}
    </AuthContext.Provider>
  );
}
