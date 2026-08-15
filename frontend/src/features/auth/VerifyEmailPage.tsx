import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import { TextField, focusFirstInvalid } from "../../ui/Field";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [formError, setFormError] = useState<string>();
  const [verified, setVerified] = useState(false);
  const [resent, setResent] = useState(false);

  const verify = useMutation({
    mutationFn: async () =>
      api<void>("/public/email-verifications", {
        method: "POST",
        body: JSON.stringify({ token }),
      }),
    onSuccess: () => {
      setVerified(true);
      setFormError(undefined);
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const resend = useMutation({
    mutationFn: async (email: string) =>
      api<void>("/public/email-verifications/resend", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
    onSuccess: () => {
      setResent(true);
      setFormError(undefined);
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onResend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    resend.mutate(String(data.get("email") ?? ""));
  }

  return (
    <AuthLayout
      title="Verifica tu correo"
      description="Confirma el enlace que te enviamos o solicita uno nuevo."
    >
      {formError ? (
        <p className="alert alert-error" role="alert">
          {formError}
        </p>
      ) : null}
      {verified ? (
        <p className="alert alert-success" role="status">
          Correo verificado. Ya puedes ingresar cuando tu empresa esté lista.
        </p>
      ) : (
        <Button
          type="button"
          onClick={() => verify.mutate()}
          loading={verify.isPending}
          disabled={!token}
        >
          Verificar correo
        </Button>
      )}
      {resent ? (
        <p className="alert alert-success" role="status">
          Si la cuenta está pendiente, te enviamos un nuevo correo.
        </p>
      ) : (
        <form className="stack" onSubmit={onResend} noValidate>
          <TextField name="email" type="email" label="Correo electrónico" required autoComplete="email" />
          <Button type="submit" variant="secondary" loading={resend.isPending}>
            Reenviar verificación
          </Button>
        </form>
      )}
      <Link to="/ingresar">Ir a ingresar</Link>
    </AuthLayout>
  );
}
