import { create } from "zustand";
import type { SessionPrincipal } from "../api/types";

type AuthState = {
  principal: SessionPrincipal | null;
  setPrincipal: (principal: SessionPrincipal | null) => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  principal: null,
  setPrincipal: (principal) => set({ principal }),
}));
