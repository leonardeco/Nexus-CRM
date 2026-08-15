import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SessionPrincipal } from "../api/types";
import { ArcoInboxPage } from "../features/arco/ArcoInboxPage";
import { PublicArcoPage } from "../features/arco/PublicArcoPage";
import { AuditPage } from "../features/audit/AuditPage";
import { AcceptInvitePage } from "../features/auth/AcceptInvitePage";
import { LoginPage } from "../features/auth/LoginPage";
import { MfaEnrollPage } from "../features/auth/MfaEnrollPage";
import { MfaPage } from "../features/auth/MfaPage";
import { ResetPasswordPage } from "../features/auth/ResetPasswordPage";
import { VerifyEmailPage } from "../features/auth/VerifyEmailPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { PolicyPage, SignupPage } from "../features/signup/SignupPage";
import { UsersPage } from "../features/users/UsersPage";
import { useAuthStore } from "../stores/auth-store";
import { AppShell } from "./AppShell";

function SessionGate({ children }: { children: ReactNode }) {
  const setPrincipal = useAuthStore((state) => state.setPrincipal);
  const sessionQuery = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const principal = await api<SessionPrincipal>("/me");
        setPrincipal(principal);
        return principal;
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          setPrincipal(null);
          return null;
        }
        throw error;
      }
    },
    retry: false,
  });

  if (sessionQuery.isLoading) {
    return <p className="muted">Cargando…</p>;
  }
  return children;
}

function RequireSession({
  children,
  admin = false,
}: {
  children: ReactNode;
  admin?: boolean;
}) {
  const principal = useAuthStore((state) => state.principal);
  const location = useLocation();

  if (!principal) {
    return <Navigate to="/ingresar" replace state={{ from: location.pathname }} />;
  }
  if (principal.scope === "mfa_enroll_only" && location.pathname !== "/ingresar/mfa/enrolar") {
    return <Navigate to="/ingresar/mfa/enrolar" replace />;
  }
  if (admin && principal.role !== "administrador") {
    return <Navigate to="/app/perfil" replace />;
  }
  return children;
}

export function AppRouter() {
  return (
    <SessionGate>
      <Routes>
        <Route path="/registro" element={<SignupPage />} />
        <Route path="/verificar-email" element={<VerifyEmailPage />} />
        <Route path="/ingresar" element={<LoginPage />} />
        <Route path="/ingresar/mfa" element={<MfaPage />} />
        <Route
          path="/ingresar/mfa/enrolar"
          element={
            <RequireSession>
              <MfaEnrollPage />
            </RequireSession>
          }
        />
        <Route path="/restablecer-contrasena" element={<ResetPasswordPage />} />
        <Route path="/invitar/aceptar" element={<AcceptInvitePage />} />
        <Route path="/t/:slug/arco" element={<PublicArcoPage />} />
        <Route path="/politica-privacidad" element={<PolicyPage kind="privacy" />} />
        <Route path="/habeas-data" element={<PolicyPage kind="habeas" />} />
        <Route
          path="/app"
          element={
            <RequireSession>
              <AppShell />
            </RequireSession>
          }
        >
          <Route path="perfil" element={<ProfilePage />} />
          <Route
            path="configuracion"
            element={
              <RequireSession admin>
                <SettingsPage />
              </RequireSession>
            }
          />
          <Route
            path="usuarios"
            element={
              <RequireSession admin>
                <UsersPage />
              </RequireSession>
            }
          />
          <Route
            path="arco"
            element={
              <RequireSession admin>
                <ArcoInboxPage />
              </RequireSession>
            }
          />
          <Route
            path="auditoria"
            element={
              <RequireSession admin>
                <AuditPage />
              </RequireSession>
            }
          />
        </Route>
        <Route path="/" element={<Navigate to="/ingresar" replace />} />
        <Route path="*" element={<Navigate to="/ingresar" replace />} />
      </Routes>
    </SessionGate>
  );
}
