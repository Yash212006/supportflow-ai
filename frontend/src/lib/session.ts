import { get, post } from './api';
import { useAuth, type User } from '@/stores/auth';

interface MeResponse { user: Omit<User, 'business_name' | 'currency' | 'customer_id'>; customer_id: string | null; business: { id: string; name: string; currency: string } }

export async function loadMe(): Promise<User> {
  const me = await get<MeResponse>('/api/auth/me');
  const user: User = { ...me.user, customer_id: me.customer_id, business_name: me.business?.name, currency: me.business?.currency };
  useAuth.getState().setUser(user);
  return user;
}

export async function signIn(email: string, password: string): Promise<User> {
  const t = await post<{ access_token: string; refresh_token: string }>('/api/auth/login', { email, password });
  useAuth.getState().setSession(t.access_token, t.refresh_token);
  return loadMe();
}

export function homeFor(u: User | null): string {
  if (!u) return '/login';
  return u.role === 'CUSTOMER' ? '/customer' : '/manager';
}
