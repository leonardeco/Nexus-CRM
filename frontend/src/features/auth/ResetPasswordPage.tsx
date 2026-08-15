import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import {
  PasswordField,
  TextField,
  focusFirstInvalid,
  passwordPolicyError,
} from "../../ui/Field";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [formError, setFormError] = useState<string>();
  const [passwordError, setPasswordError] = useState<string>();
  const [requested, setRequested] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const requestReset = useMutation({
    mutationFn: async (email: string) =>
      api<void>("/public/password-resets", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
    onSuccess: () => {
      setRequested(true);
      setFormError(undefined);
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const confirmReset = useMutation({
    mutationFn: async (password: string) =>
      api<void>("/public/password-resets/confirm", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      }),
    onSuccess: () => {
      setConfirmed(true);
      setFormError(undefined);
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    requestReset.mutate(String(new FormData(form).get("email") ?? ""));
  }

  function onConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = String(new FormData(form).get("password") ?? "");
    const policy = passwordPolicyError(password);
    setPasswordError(policy);
    if (policy || !form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    confirmReset.mutate(password);
  }

  if (token) {
    return (
      <AuthLayout title="Elige una contraseña nueva">
        {confirmed ? (
          <p className="alert alert-success" role="status">
            Contraseña actualizada. Ya puedes ingresar.
          </p>
        ) : (
          <form className="stack" onSubmit={onConfirm} noValidate>
            {formError ? (
              <p className="alert alert-error" role="alert">
                {formError}
              </p>
            ) : null}
            <PasswordField
              name="password"
              label="Nueva contraseña"
              required
              autoComplete="new-password"
              error={passwordError}
              onBlur={(event) => setPasswordError(passwordPolicyError(event.currentTarget.value))}
            />
            <Button type="submit" loading={confirmReset.isPending}>
              Guardar contraseña
            </Button>
          </form>
        )}
        <Link to="/ingresar">Ingresar</Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Restablecer contraseña"
      description="Te enviaremos un enlace si el correo está registrado."
    >
      {requested ? (
        <p className="alert alert-success" role="status">
          Si el correo existe, te enviamos instrucciones para restablecer la contraseña.
        </p>
      ) : (
        <form className="stack" onSubmit={onRequest} noValidate>
          {formError ? (
            <p className="alert alert-error" role="alert">
              {formError}
            </p>
          ) : null}
          <TextField name="email" type="email" label="Correo electrónico" required autoComplete="email" />
          <Button type="submit" loading={requestReset.isPending}>
            Enviar enlace
          </Button>
        </form>
      )}
      <Link to="/ingresar">Volver a ingresar</Link>
    </AuthLayout>
  );
}
