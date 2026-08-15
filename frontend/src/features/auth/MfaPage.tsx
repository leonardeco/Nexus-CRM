import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { SessionPrincipal } from "../../api/types";
import { useAuthStore } from "../../stores/auth-store";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import { TextField, focusFirstInvalid } from "../../ui/Field";

export function MfaPage() {
  const [params] = useSearchParams();
  const challengeId = params.get("challenge") ?? "";
  const navigate = useNavigate();
  const setPrincipal = useAuthStore((state) => state.setPrincipal);
  const [formError, setFormError] = useState<string>();

  const mutation = useMutation({
    mutationFn: async (code: string) =>
      api<SessionPrincipal>("/public/sessions/mfa", {
        method: "POST",
        body: JSON.stringify({ challengeId, code }),
      }),
    onSuccess: (principal) => {
      setPrincipal(principal);
      navigate("/app/perfil", { replace: true });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    mutation.mutate(String(data.get("code") ?? ""));
  }

  return (
    <AuthLayout
      title="Verificación en dos pasos"
      description="Ingresa el código de tu aplicación de autenticación o un código de respaldo."
    >
      <form className="stack" onSubmit={onSubmit} noValidate>
        {formError ? (
          <p className="alert alert-error" role="alert">
            {formError}
          </p>
        ) : null}
        <TextField name="code" label="Código" required autoComplete="one-time-code" inputMode="numeric" />
        <Button type="submit" loading={mutation.isPending} disabled={!challengeId}>
          Verificar
        </Button>
      </form>
    </AuthLayout>
  );
}
