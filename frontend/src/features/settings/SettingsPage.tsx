import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, problemMessage } from "../../api/client";
import type { Tenant } from "../../api/types";
import { Button } from "../../ui/Button";
import { TextField, focusFirstInvalid } from "../../ui/Field";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string>();
  const [status, setStatus] = useState<string>();

  const tenantQuery = useQuery({
    queryKey: ["tenant"],
    queryFn: () => api<Tenant>("/tenant"),
  });

  const mutation = useMutation({
    mutationFn: async (body: { companyName: string; slug: string }) =>
      api<Tenant>("/tenant", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (tenant) => {
      queryClient.setQueryData(["tenant"], tenant);
      setStatus("Cambios guardados.");
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
      companyName: String(data.get("companyName") ?? ""),
      slug: String(data.get("slug") ?? ""),
    });
  }

  const tenant = tenantQuery.data;

  return (
    <div className="stack-lg">
      <h1>Configuración</h1>
      {tenantQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(tenantQuery.error)}
        </p>
      ) : null}
      {tenant ? (
        <form className="stack" onSubmit={onSubmit} noValidate>
          {formError ? (
            <p className="alert alert-error" role="alert">
              {formError}
            </p>
          ) : null}
          {status ? (
            <p className="alert alert-success" role="status" aria-live="polite">
              {status}
            </p>
          ) : null}
          <TextField
            name="companyName"
            label="Nombre de la empresa"
            required
            defaultValue={tenant.companyName}
          />
          <TextField
            name="slug"
            label="Identificador público"
            required
            pattern="[a-z0-9-]{3,63}"
            defaultValue={tenant.slug}
            hint={`Formulario ARCO público: /t/${tenant.slug}/arco`}
          />
          <p className="muted">
            Plan {tenant.plan} · Cupo {tenant.seatCap} personas
          </p>
          <Button type="submit" loading={mutation.isPending}>
            Guardar
          </Button>
        </form>
      ) : (
        <p className="muted">Cargando…</p>
      )}
    </div>
  );
}
