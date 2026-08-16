import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type {
  Contact,
  ConsentBasis,
  ConsentStatus,
  User,
} from "../../api/types";
import { Button } from "../../ui/Button";
import {
  SelectField,
  TextAreaField,
  TextField,
  focusFirstInvalid,
} from "../../ui/Field";

const CONSENT_STATUS: { value: ConsentStatus; label: string }[] = [
  { value: "unknown", label: "Sin registrar" },
  { value: "granted", label: "Otorgado" },
  { value: "denied", label: "Rechazado" },
];

const CONSENT_BASIS: { value: ConsentBasis; label: string }[] = [
  { value: "consentimiento", label: "Consentimiento" },
  { value: "contrato", label: "Contrato" },
  { value: "interes_legitimo", label: "Interés legítimo" },
  { value: "obligacion_legal", label: "Obligación legal" },
];

export function ContactDetailPage() {
  const { contactId = "" } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string>();
  const [status, setStatus] = useState<string>();

  const contactQuery = useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => api<Contact>(`/contacts/${contactId}`),
  });

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });

  function invalidate() {
    return queryClient.invalidateQueries({ queryKey: ["contact", contactId] });
  }

  const update = useMutation({
    mutationFn: async (changes: Partial<Contact>) =>
      api<Contact>(`/contacts/${contactId}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      }),
    onSuccess: async () => {
      setStatus("Contacto actualizado.");
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const recordConsent = useMutation({
    mutationFn: async (body: { status: ConsentStatus; basis?: ConsentBasis }) =>
      api<Contact>(`/contacts/${contactId}/consent`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setStatus("Consentimiento registrado.");
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const assign = useMutation({
    mutationFn: async (ownerUserId: string | null) =>
      api<Contact>(`/contacts/${contactId}/assignment`, {
        method: "POST",
        body: JSON.stringify({ ownerUserId }),
      }),
    onSuccess: async () => {
      setStatus("Responsable actualizado.");
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const archive = useMutation({
    mutationFn: async () =>
      api<void>(`/contacts/${contactId}/archive`, { method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["contacts"] });
      navigate("/app/contactos");
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  if (contactQuery.isError) {
    return (
      <div className="stack-lg">
        <h1>Contacto</h1>
        <p className="alert alert-error" role="alert">
          {problemMessage(contactQuery.error)}
        </p>
        <Link to="/app/contactos">Volver a contactos</Link>
      </div>
    );
  }

  if (contactQuery.isLoading || !contactQuery.data) {
    return (
      <div className="stack-lg">
        <h1>Contacto</h1>
        <p className="muted">Cargando…</p>
      </div>
    );
  }

  const contact = contactQuery.data;
  const users = usersQuery.data ?? [];

  function onUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    update.mutate({
      fullName: String(data.get("fullName") ?? ""),
      jobTitle: String(data.get("jobTitle") ?? "") || null,
      primaryEmail: String(data.get("primaryEmail") ?? "") || null,
      primaryPhone: String(data.get("primaryPhone") ?? "") || null,
      address: String(data.get("address") ?? "") || null,
      notes: String(data.get("notes") ?? "") || null,
    });
  }

  function onConsent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const nextStatus = String(data.get("status") ?? "unknown") as ConsentStatus;
    const basis = String(data.get("basis") ?? "") as ConsentBasis | "";
    recordConsent.mutate({
      status: nextStatus,
      basis: basis || undefined,
    });
  }

  return (
    <div className="stack-lg">
      <p>
        <Link to="/app/contactos">← Contactos</Link>
      </p>
      <h1>{contact.fullName}</h1>
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

      <section className="stack" aria-labelledby="datos-contacto">
        <h2 id="datos-contacto">Datos</h2>
        <form className="stack" onSubmit={onUpdate} noValidate>
          <TextField name="fullName" label="Nombre completo" required defaultValue={contact.fullName} />
          <TextField name="jobTitle" label="Cargo" defaultValue={contact.jobTitle ?? ""} />
          <TextField name="primaryEmail" type="email" label="Correo principal" defaultValue={contact.primaryEmail ?? ""} />
          <TextField name="primaryPhone" label="Teléfono principal" defaultValue={contact.primaryPhone ?? ""} />
          <TextField name="address" label="Dirección" defaultValue={contact.address ?? ""} />
          <TextAreaField name="notes" label="Notas" defaultValue={contact.notes ?? ""} />
          <Button type="submit" loading={update.isPending}>
            Guardar cambios
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="consentimiento">
        <h2 id="consentimiento">Habeas data</h2>
        <form className="stack" onSubmit={onConsent} noValidate>
          <SelectField name="status" label="Estado" defaultValue={contact.consentStatus}>
            {CONSENT_STATUS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </SelectField>
          <SelectField name="basis" label="Base de tratamiento" defaultValue={contact.consentBasis ?? ""}>
            <option value="">Sin base</option>
            {CONSENT_BASIS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </SelectField>
          <Button type="submit" variant="secondary" loading={recordConsent.isPending}>
            Registrar consentimiento
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="responsable">
        <h2 id="responsable">Responsable</h2>
        <SelectField
          name="ownerUserId"
          label="Asignar a"
          value={contact.ownerUserId ?? ""}
          onChange={(event) => assign.mutate(event.currentTarget.value || null)}
        >
          <option value="">Sin asignar</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.fullName}
            </option>
          ))}
        </SelectField>
      </section>

      <section className="stack" aria-labelledby="archivar">
        <h2 id="archivar">Archivar</h2>
        <Button variant="danger" onClick={() => archive.mutate()} loading={archive.isPending}>
          Archivar contacto
        </Button>
      </section>
    </div>
  );
}
