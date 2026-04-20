import { apiLogin, apiRegister, apiGetCurrentUser } from './api';

export interface User {
  email: string;
  plan: 'free' | 'pro' | 'business';
}

const TOKEN_KEY = 'ocin_jwt_token';
const USER_KEY = 'ocin_user';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export async function login(email: string, password: string): Promise<{ token: string; user: User }> {
  const result = await apiLogin(email, password);
  localStorage.setItem(TOKEN_KEY, result.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(result.user));
  return { token: result.access_token, user: result.user };
}

export async function register(email: string, password: string, plan: User['plan']): Promise<{ token: string; user: User }> {
  const result = await apiRegister(email, password, plan);
  localStorage.setItem(TOKEN_KEY, result.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(result.user));
  return { token: result.access_token, user: result.user };
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  try {
    // JWT is base64url encoded, split by '.' to get payload
    const parts = token.split('.');
    if (parts.length !== 3) return false;

    // Decode the payload (middle part)
    const payloadBase64 = parts[1];
    // Add padding if needed
    const padded = payloadBase64 + '='.repeat((4 - payloadBase64.length % 4) % 4);
    const payload = JSON.parse(atob(padded.replace(/-/g, '+').replace(/_/g, '/')));

    // Check if token is expired
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}
