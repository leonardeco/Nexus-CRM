import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { SessionPrincipal } from "../../api/types";
import { useAuthStore } from "../../stores/auth-store";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import {
  PasswordField,
  focusFirstInvalid,
  passwordPolicyError,
} from "../../ui/Field";

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const setPrincipal = useAuthStore((state) => state.setPrincipal);
  const [formError, setFormError] = useState<string>();
  const [passwordError, setPasswordError] = useState<string>();

  const mutation = useMutation({
    mutationFn: async (password: string) =>
      api<SessionPrincipal>("/public/invites/accept", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      }),
    onSuccess: (principal) => {
      setPrincipal(principal);
      if (principal.scope === "mfa_enroll_only") {
        navigate("/ingresar/mfa/enrolar", { replace: true });
        return;
      }
      navigate("/app/perfil", { replace: true });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = String(new FormData(form).get("password") ?? "");
    const policy = passwordPolicyError(password);
    setPasswordError(policy);
    if (policy || !form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    mutation.mutate(password);
  }

  return (
    <AuthLayout
      title="Aceptar invitación"
      description="Crea tu contraseña para unirte a la empresa."
    >
      <form className="stack" onSubmit={onSubmit} noValidate>
        {formError ? (
          <p className="alert alert-error" role="alert">
            {formError}
          </p>
        ) : null}
        <PasswordField
          name="password"
          label="Contraseña"
          required
          autoComplete="new-password"
          error={passwordError}
          onBlur={(event) => setPasswordError(passwordPolicyError(event.currentTarget.value))}
        />
        <Button type="submit" loading={mutation.isPending} disabled={!token}>
          Unirme
        </Button>
      </form>
    </AuthLayout>
  );
}
