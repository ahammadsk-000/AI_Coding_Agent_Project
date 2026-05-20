/**
 * Auth store — holds tokens + user, persists to localStorage.
 *
 * Tokens are the source of truth for "am I logged in"; user is hydrated on
 * boot via /me. We persist only what's necessary.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { User } from "@/lib/api";

interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  accessExpiresAt: string;
  refreshExpiresAt: string;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  accessExpiresAt: string | null;
  refreshExpiresAt: string | null;
  user: User | null;
  hydrated: boolean;

  setTokens: (t: AuthTokens) => void;
  setUser: (u: User | null) => void;
  setHydrated: (v: boolean) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      accessExpiresAt: null,
      refreshExpiresAt: null,
      user: null,
      hydrated: false,

      setTokens: (t) =>
        set({
          accessToken: t.accessToken,
          refreshToken: t.refreshToken,
          accessExpiresAt: t.accessExpiresAt,
          refreshExpiresAt: t.refreshExpiresAt,
        }),
      setUser: (u) => set({ user: u }),
      setHydrated: (v) => set({ hydrated: v }),
      clear: () =>
        set({
          accessToken: null,
          refreshToken: null,
          accessExpiresAt: null,
          refreshExpiresAt: null,
          user: null,
        }),
    }),
    {
      name: "aca.auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        accessExpiresAt: s.accessExpiresAt,
        refreshExpiresAt: s.refreshExpiresAt,
      }),
    },
  ),
);
