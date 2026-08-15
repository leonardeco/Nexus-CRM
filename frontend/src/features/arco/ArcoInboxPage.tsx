import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, problemMessage } from "../../api/client";
import type { ArcoRequest } from "../../api/types";
import { Button } from "../../ui/Button";
import {
  SelectField,
  TextAreaField,
  TextField,
  focusFirstInvalid,
} from "../../ui/Field";
import { ARCO_OPTIONS } from "./PublicArcoPage";

export function ArcoInboxPage() {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string>();
  const [responseDrafts, setResponseDrafts] = useState<Record<string, string>>({});

  const inboxQuery = useQuery({
    queryKey: ["arco-inbox"],
    queryFn: () => api<ArcoRequest[]>("/arco-requests"),
  });

  const intake = useMutation({
    mutationFn: async (body: Record<string, unknown>) =>
      api<ArcoRequest>("/arco-requests", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setFormError(undefined);
      await queryClient.invalidateQueries({ queryKey: ["arco-inbox"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const respond = useMutation({
    mutationFn: async (input: { id: string; responseText: string }) =>
      api<ArcoRequest>(`/arco-requests/${input.id}/response`, {
        method: "POST",
        body: JSON.stringify({ responseText: input.responseText }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["arco-inbox"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const close = useMutation({
    mutationFn: async (id: string) =>
      api<ArcoRequest>(`/arco-requests/${id}/closure`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["arco-inbox"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onIntake(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    intake.mutate({
      requestType: String(data.get("requestType") ?? ""),
      requesterName: String(data.get("requesterName") ?? ""),
      requesterEmail: String(data.get("requesterEmail") ?? ""),
      details: String(data.get("details") ?? ""),
    });
    form.reset();
  }

  const items = inboxQuery.data ?? [];

  return (
    <div className="stack-lg">
      <h1>Bandeja ARCO</h1>
      {formError ? (
        <p className="alert alert-error" role="alert">
          {formError}
        </p>
      ) : null}
      <section className="stack" aria-labelledby="manual">
        <h2 id="manual">Registro manual (correo)</h2>
        <form className="stack" onSubmit={onIntake} noValidate>
          <TextField name="requesterName" label="Nombre de quien solicita" required />
          <TextField name="requesterEmail" type="email" label="Correo" required />
          <SelectField name="requestType" label="Tipo de solicitud" required>
            <option value="">Selecciona un tipo</option>
            {ARCO_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </SelectField>
          <TextAreaField name="details" label="Detalles" required />
          <Button type="submit" loading={intake.isPending}>
            Registrar
          </Button>
        </form>
      </section>
      <ul className="stack">
        {items.map((item) => (
          <li key={item.id} className="auth-card stack">
            <h3>
              {item.requestType} · {item.status}
            </h3>
            <p>
              {item.requesterName} · {item.requesterEmail}
            </p>
            {item.details ? <p>{item.details}</p> : null}
            {item.status === "open" ? (
              <div className="stack">
                <TextAreaField
                  label={`Respuesta para ${item.requesterName}`}
                  value={responseDrafts[item.id] ?? ""}
                  onChange={(event) =>
                    setResponseDrafts((current) => ({
                      ...current,
                      [item.id]: event.currentTarget.value,
                    }))
                  }
                />
                <Button
                  type="button"
                  onClick={() =>
                    respond.mutate({
                      id: item.id,
                      responseText: responseDrafts[item.id] ?? "",
                    })
                  }
                  loading={respond.isPending}
                >
                  Responder
                </Button>
              </div>
            ) : null}
            {item.status === "responded" ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => close.mutate(item.id)}
                loading={close.isPending}
              >
                Cerrar
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
