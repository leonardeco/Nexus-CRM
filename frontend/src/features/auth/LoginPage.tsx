import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { LoginResponse } from "../../api/types";
import { useAuthStore } from "../../stores/auth-store";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import { PasswordField, TextField, focusFirstInvalid } from "../../ui/Field";

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setPrincipal = useAuthStore((state) => state.setPrincipal);
  const setMfaChallengeId = useAuthStore((state) => state.setMfaChallengeId);
  const [formError, setFormError] = useState<string>();

  const mutation = useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      api<LoginResponse>("/public/sessions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (result) => {
      if (result.status === "authenticated" && result.principal) {
        queryClient.setQueryData(["me"], result.principal);
        setPrincipal(result.principal);
        navigate("/app/perfil", { replace: true });
        return;
      }
      if (result.status === "mfa_enrollment_required") {
        if (result.principal) {
          queryClient.setQueryData(["me"], result.principal);
          setPrincipal(result.principal);
        }
        navigate("/ingresar/mfa/enrolar", { replace: true });
        return;
      }
      if (result.status === "mfa_required" && result.mfaChallengeId) {
        setMfaChallengeId(result.mfaChallengeId);
        navigate("/ingresar/mfa", { replace: true });
      }
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
    mutation.mutate({
      email: String(data.get("email") ?? ""),
      password: String(data.get("password") ?? ""),
    });
  }

  return (
    <AuthLayout title="Ingresar" description="Entra con tu correo y contraseña.">
      <form className="stack" onSubmit={onSubmit} noValidate>
        {formError ? (
          <p className="alert alert-error" role="alert">
            {formError}
          </p>
        ) : null}
        <TextField name="email" type="email" label="Correo electrónico" required autoComplete="username" />
        <PasswordField
          name="password"
          label="Contraseña"
          required
          autoComplete="current-password"
        />
        <Button type="submit" loading={mutation.isPending}>
          Ingresar
        </Button>
      </form>
      <p className="muted">
        <Link to="/restablecer-contrasena">Olvidé mi contraseña</Link>
      </p>
      <p className="muted">
        ¿No tienes cuenta? <Link to="/registro">Crear empresa</Link>
      </p>
    </AuthLayout>
  );
}
