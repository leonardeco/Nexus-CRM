import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Smartphone } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { SessionPrincipal } from "../../api/types";
import { useAuthStore } from "../../stores/auth-store";
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

function isOtpauthUrl(url: string): boolean {
  try {
    return new URL(url).protocol === "otpauth:";
  } catch {
    return false;
  }
}

export function MfaEnrollPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const principal = useAuthStore((state) => state.principal);
  const setPrincipal = useAuthStore((state) => state.setPrincipal);
  const [formError, setFormError] = useState<string>();
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [codesSaved, setCodesSaved] = useState(false);
  const started = useRef(false);

  const enroll = useMutation({
    mutationFn: () => api<{ otpauthUrl: string }>("/me/mfa/totp", { method: "POST" }),
  });

  const startEnroll = enroll.mutate;

  useEffect(() => {
    if (started.current) {
      return;
    }
    started.current = true;
    startEnroll();
  }, [startEnroll]);

  const confirm = useMutation({
    mutationFn: async (body: { code: string; backupCodesSaved: true }) =>
      api<{ backupCodes: string[] }>("/me/mfa/totp/confirm", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (result) => {
      setBackupCodes(result.backupCodes);
      setFormError(undefined);
      const updated: SessionPrincipal | null = principal
        ? { ...principal, scope: "full", mfaStatus: "enrolled" }
        : principal;
      if (updated) {
        queryClient.setQueryData(["me"], updated);
        setPrincipal(updated);
      }
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const otpauthUrl = enroll.data?.otpauthUrl ?? "";
  const secret = useMemo(
    () => (otpauthUrl ? secretFromOtpauth(otpauthUrl) : ""),
    [otpauthUrl],
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
        <label className="consent-label">
          <input
            type="checkbox"
            name="backupCodesSaved"
            required
            checked={codesSaved}
            onChange={(event) => setCodesSaved(event.currentTarget.checked)}
          />
          <span>
            Ya guardé los códigos
            <span className="req" aria-hidden="true">
              {" "}
              *
            </span>
          </span>
        </label>
        <Button
          type="button"
          onClick={() => navigate("/app/perfil", { replace: true })}
          disabled={!codesSaved}
        >
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
      {enroll.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(enroll.error)}
        </p>
      ) : null}
      {enroll.data ? (
        <div className="stack">
          <Smartphone size={24} aria-hidden="true" />
          <p className="muted">Clave secreta</p>
          <p className="secret-box">{secret}</p>
          {isOtpauthUrl(otpauthUrl) ? (
            <a href={otpauthUrl}>Abrir en la aplicación de autenticación</a>
          ) : null}
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
        <Button type="submit" loading={confirm.isPending} disabled={!enroll.data}>
          Confirmar
        </Button>
      </form>
    </AuthLayout>
  );
}
