import { createContext } from 'react';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  picture: string;
}

export interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
