import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { ArcoRequest, ArcoRequestType } from "../../api/types";
import { AuthLayout } from "../../ui/AuthLayout";
import { Button } from "../../ui/Button";
import { SelectField, TextAreaField, TextField, focusFirstInvalid } from "../../ui/Field";

const ARCO_OPTIONS: { value: ArcoRequestType; label: string }[] = [
  { value: "acceso", label: "acceso" },
  { value: "rectificacion", label: "rectificación" },
  { value: "cancelacion", label: "cancelación" },
  { value: "oposicion", label: "oposición" },
];

export function PublicArcoPage() {
  const { slug = "" } = useParams();
  const [formError, setFormError] = useState<string>();
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: async (body: Record<string, unknown>) =>
      api<ArcoRequest>(`/public/tenants/${encodeURIComponent(slug)}/arco-requests`, {
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
      requesterName: String(data.get("requesterName") ?? ""),
      requesterEmail: String(data.get("requesterEmail") ?? ""),
      requestType: String(data.get("requestType") ?? ""),
      details: String(data.get("details") ?? ""),
    });
  }

  return (
    <AuthLayout
      title="Solicitud ARCO"
      description="Ejercicio de acceso, rectificación, cancelación u oposición. No se crea una sesión."
    >
      {done ? (
        <p className="alert alert-success" role="status">
          Recibimos tu solicitud. Te contactaremos al correo indicado.
        </p>
      ) : (
        <form className="stack" onSubmit={onSubmit} noValidate>
          {formError ? (
            <p className="alert alert-error" role="alert">
              {formError}
            </p>
          ) : null}
          <TextField name="requesterName" label="Nombre" required autoComplete="name" />
          <TextField
            name="requesterEmail"
            type="email"
            label="Correo electrónico"
            required
            autoComplete="email"
          />
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
    </AuthLayout>
  );
}

export { ARCO_OPTIONS };
