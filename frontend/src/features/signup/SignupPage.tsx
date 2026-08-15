import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import { POLICY_VERSION } from "../../api/types";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import {
  PasswordField,
  TextField,
  focusFirstInvalid,
  passwordPolicyError,
} from "../../ui/Field";

export function SignupPage() {
  const [passwordError, setPasswordError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      await api<void>("/public/signups", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setDone(true);
      setFormError(undefined);
    },
    onError: (error) => {
      setFormError(problemMessage(error));
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("password") ?? "");
    const policy = passwordPolicyError(password);
    setPasswordError(policy);
    if (policy || !form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    mutation.mutate({
      companyName: String(data.get("companyName") ?? ""),
      slug: String(data.get("slug") ?? ""),
      adminFullName: String(data.get("adminFullName") ?? ""),
      email: String(data.get("email") ?? ""),
      password,
      acceptPrivacyPolicy: true,
      acceptHabeasData: true,
      policyVersion: POLICY_VERSION,
    });
  }

  return (
    <AuthLayout
      title="Crea tu empresa"
      description="Regístrate para empezar. Te enviaremos un correo de verificación."
    >
      {done ? (
        <p className="alert alert-success" role="status">
          Si los datos son válidos, te enviamos un correo para verificar tu cuenta.
        </p>
      ) : (
        <form className="stack" onSubmit={onSubmit} noValidate>
          {formError ? (
            <p className="alert alert-error" role="alert">
              {formError}
            </p>
          ) : null}
          <TextField name="companyName" label="Nombre de la empresa" required autoComplete="organization" />
          <TextField
            name="slug"
            label="Identificador público"
            required
            pattern="[a-z0-9-]{3,63}"
            hint="Solo minúsculas, números y guiones. Se usa en /t/tu-empresa/arco"
          />
          <TextField name="adminFullName" label="Tu nombre completo" required autoComplete="name" />
          <TextField name="email" type="email" label="Correo electrónico" required autoComplete="email" />
          <PasswordField
            name="password"
            label="Contraseña"
            required
            autoComplete="new-password"
            error={passwordError}
            hint="Mínimo 10 caracteres, con mayúscula, minúscula y dígito."
            onBlur={(event) => setPasswordError(passwordPolicyError(event.currentTarget.value))}
          />
          <div className="consent-row">
            <label className="consent-label">
              <input type="checkbox" name="acceptPrivacyPolicy" required />
              <span>
                Acepto la política de privacidad
                <span className="req" aria-hidden="true">
                  {" "}
                  *
                </span>
              </span>
            </label>
            <a href="/politica-privacidad">política de privacidad</a>
          </div>
          <div className="consent-row">
            <label className="consent-label">
              <input type="checkbox" name="acceptHabeasData" required />
              <span>
                Acepto el tratamiento de datos personales (habeas data)
                <span className="req" aria-hidden="true">
                  {" "}
                  *
                </span>
              </span>
            </label>
            <a href="/habeas-data">habeas data</a>
          </div>
          <Button type="submit" loading={mutation.isPending}>
            Crear empresa
          </Button>
        </form>
      )}
      <p className="muted">
        ¿Ya tienes cuenta? <Link to="/ingresar">Ingresar</Link>
      </p>
    </AuthLayout>
  );
}

export function PolicyPage({ kind }: { kind: "privacy" | "habeas" }) {
  const title =
    kind === "privacy" ? "Política de privacidad" : "Tratamiento de datos personales";
  return (
    <AuthLayout title={title} description={`Versión ${POLICY_VERSION}`}>
      <div className="stack">
        <p>
          NEXUS CRM trata datos de identificación y contacto para prestar el servicio de
          gestión comercial y atender solicitudes ARCO según la Ley 1581 de 2012.
        </p>
        <p className="muted">
          Conservamos el consentimiento, la versión de esta política y la dirección IP del
          registro. Puedes ejercer acceso, rectificación, cancelación y oposición en la
          URL pública de tu empresa o desde tu perfil.
        </p>
        <Link to="/registro">Volver al registro</Link>
      </div>
    </AuthLayout>
  );
}
