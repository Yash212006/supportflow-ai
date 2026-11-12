import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Role = 'CUSTOMER' | 'SUPPORT_AGENT' | 'SUPPORT_MANAGER' | 'ADMIN';
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  business_id: string;
  business_name?: string;
  currency?: string;
  customer_id?: string | null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  setSession: (access: string, refresh: string, user?: User | null) => void;
  setUser: (u: User) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: (accessToken, refreshToken, user) => set((s) => ({ accessToken, refreshToken, user: user ?? s.user })),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: 'supportflow-auth' },
  ),
);

export const isStaff = (r?: Role) => r === 'SUPPORT_AGENT' || r === 'SUPPORT_MANAGER' || r === 'ADMIN';
export const isManager = (r?: Role) => r === 'SUPPORT_MANAGER' || r === 'ADMIN';
