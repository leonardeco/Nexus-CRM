import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, problemMessage } from "../../api/client";
import type { ArcoRequest } from "../../api/types";
import { useAuthStore } from "../../stores/auth-store";
import { Button } from "../../ui/Button";
import { SelectField, TextAreaField, focusFirstInvalid } from "../../ui/Field";
import { ARCO_OPTIONS } from "../arco/PublicArcoPage";

export function ProfilePage() {
  const principal = useAuthStore((state) => state.principal);
  const [formError, setFormError] = useState<string>();
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: async (body: Record<string, unknown>) =>
      api<ArcoRequest>("/me/arco-requests", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setDone(true);
      setFormError(undefined);
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
      requestType: String(data.get("requestType") ?? ""),
      details: String(data.get("details") ?? ""),
    });
  }

  return (
    <div className="stack-lg">
      <h1>Perfil</h1>
      {principal ? (
        <div className="stack">
          <p>
            <strong>{principal.fullName}</strong>
          </p>
          <p className="muted">{principal.email}</p>
          <p className="muted">Rol: {principal.role}</p>
        </div>
      ) : null}
      <section className="stack" aria-labelledby="arco-propia">
        <h2 id="arco-propia">Solicitud ARCO sobre tu cuenta</h2>
        {done ? (
          <p className="alert alert-success" role="status">
            Recibimos tu solicitud.
          </p>
        ) : (
          <form className="stack" onSubmit={onSubmit} noValidate>
            {formError ? (
              <p className="alert alert-error" role="alert">
                {formError}
              </p>
            ) : null}
            <SelectField name="requestType" label="Tipo de solicitud" required>
              <option value="">Selecciona un tipo</option>
              {ARCO_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <TextAreaField name="details" label="Detalles" required />
            <Button type="submit" loading={mutation.isPending}>
              Enviar solicitud
            </Button>
          </form>
        )}
      </section>
    </div>
  );
}
