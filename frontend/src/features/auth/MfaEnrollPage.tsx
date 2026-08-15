import { useMutation, useQuery } from "@tanstack/react-query";
import { Smartphone } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import { TextField, focusFirstInvalid } from "../../ui/Field";

function secretFromOtpauth(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.searchParams.get("secret") ?? url;
  } catch {
    return url;
  }
}

export function MfaEnrollPage() {
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string>();
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);

  const enrollQuery = useQuery({
    queryKey: ["mfa-enroll"],
    queryFn: () => api<{ otpauthUrl: string }>("/me/mfa/totp", { method: "POST" }),
  });

  const confirm = useMutation({
    mutationFn: async (body: { code: string; backupCodesSaved: true }) =>
      api<{ backupCodes: string[] }>("/me/mfa/totp/confirm", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (result) => {
      setBackupCodes(result.backupCodes);
      setFormError(undefined);
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const secret = useMemo(
    () => (enrollQuery.data ? secretFromOtpauth(enrollQuery.data.otpauthUrl) : ""),
    [enrollQuery.data],
  );

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    confirm.mutate({
      code: String(data.get("code") ?? ""),
      backupCodesSaved: true,
    });
  }

  if (backupCodes) {
    return (
      <AuthLayout
        title="Guarda tus códigos de respaldo"
        description="Estos códigos se muestran una sola vez. Úsalos si pierdes el autenticador."
      >
        <ul className="codes">
          {backupCodes.map((code) => (
            <li key={code}>
              <code>{code}</code>
            </li>
          ))}
        </ul>
        <Button type="button" onClick={() => navigate("/app/perfil", { replace: true })}>
          Continuar al perfil
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Activa la verificación en dos pasos"
      description="Escanea o ingresa la clave en tu aplicación de autenticación. Confirma con un código."
    >
      {enrollQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(enrollQuery.error)}
        </p>
      ) : null}
      {enrollQuery.data ? (
        <div className="stack">
          <Smartphone size={24} aria-hidden="true" />
          <p className="muted">Clave secreta</p>
          <p className="secret-box">{secret}</p>
          <a href={enrollQuery.data.otpauthUrl}>Abrir en la aplicación de autenticación</a>
        </div>
      ) : (
        <p className="muted">Preparando tu clave…</p>
      )}
      <form className="stack" onSubmit={onSubmit} noValidate>
        {formError ? (
          <p className="alert alert-error" role="alert">
            {formError}
          </p>
        ) : null}
        <TextField name="code" label="Código de la aplicación" required autoComplete="one-time-code" />
        <label className="consent-label">
          <input type="checkbox" name="backupCodesSaved" required />
          <span>
            Ya guardé los códigos
            <span className="req" aria-hidden="true">
              {" "}
              *
            </span>
          </span>
        </label>
        <p className="muted">
          Al confirmar verás 10 códigos de respaldo. Guárdalos antes de continuar.
        </p>
        <Button type="submit" loading={confirm.isPending} disabled={!enrollQuery.data}>
          Confirmar
        </Button>
      </form>
    </AuthLayout>
  );
}
