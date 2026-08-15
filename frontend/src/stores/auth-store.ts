import { create } from "zustand";
import type { SessionPrincipal } from "../api/types";

type AuthState = {
  principal: SessionPrincipal | null;
  mfaChallengeId: string | null;
  setPrincipal: (principal: SessionPrincipal | null) => void;
  setMfaChallengeId: (challengeId: string | null) => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  principal: null,
  mfaChallengeId: null,
  setPrincipal: (principal) => set({ principal }),
  setMfaChallengeId: (mfaChallengeId) => set({ mfaChallengeId }),
}));
