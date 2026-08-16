import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { Account, Contact } from "../../api/types";
import { Button } from "../../ui/Button";
import { TextAreaField, TextField, focusFirstInvalid } from "../../ui/Field";

export function AccountDetailPage() {
  const { accountId = "" } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string>();
  const [status, setStatus] = useState<string>();

  const accountQuery = useQuery({
    queryKey: ["account", accountId],
    queryFn: () => api<Account>(`/accounts/${accountId}`),
  });

  const contactsQuery = useQuery({
    queryKey: ["account", accountId, "contacts"],
    queryFn: () => api<Contact[]>(`/accounts/${accountId}/contacts`),
  });

  const update = useMutation({
    mutationFn: async (changes: Partial<Account>) =>
      api<Account>(`/accounts/${accountId}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      }),
    onSuccess: async () => {
      setStatus("Cuenta actualizada.");
      setFormError(undefined);
      await queryClient.invalidateQueries({ queryKey: ["account", accountId] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const archive = useMutation({
    mutationFn: async () =>
      api<void>(`/accounts/${accountId}/archive`, { method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["accounts"] });
      navigate("/app/cuentas");
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  if (accountQuery.isError) {
    return (
      <div className="stack-lg">
        <h1>Cuenta</h1>
        <p className="alert alert-error" role="alert">
          {problemMessage(accountQuery.error)}
        </p>
        <Link to="/app/cuentas">Volver a cuentas</Link>
      </div>
    );
  }

  if (accountQuery.isLoading || !accountQuery.data) {
    return (
      <div className="stack-lg">
        <h1>Cuenta</h1>
        <p className="muted">Cargando…</p>
      </div>
    );
  }

  const account = accountQuery.data;
  const contacts = contactsQuery.data ?? [];

  function onUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    update.mutate({
      name: String(data.get("name") ?? ""),
      industry: String(data.get("industry") ?? "") || null,
      region: String(data.get("region") ?? "") || null,
      website: String(data.get("website") ?? "") || null,
      phone: String(data.get("phone") ?? "") || null,
      notes: String(data.get("notes") ?? "") || null,
    });
  }

  return (
    <div className="stack-lg">
      <p>
        <Link to="/app/cuentas">← Cuentas</Link>
      </p>
      <h1>{account.name}</h1>
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

      <section className="stack" aria-labelledby="datos-cuenta">
        <h2 id="datos-cuenta">Datos</h2>
        <form className="stack" onSubmit={onUpdate} noValidate>
          <TextField name="name" label="Nombre" required defaultValue={account.name} />
          <TextField name="industry" label="Industria" defaultValue={account.industry ?? ""} />
          <TextField name="region" label="Región" defaultValue={account.region ?? ""} />
          <TextField name="website" label="Sitio web" defaultValue={account.website ?? ""} />
          <TextField name="phone" label="Teléfono" defaultValue={account.phone ?? ""} />
          <TextAreaField name="notes" label="Notas" defaultValue={account.notes ?? ""} />
          <Button type="submit" loading={update.isPending}>
            Guardar cambios
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="contactos-cuenta">
        <h2 id="contactos-cuenta">Contactos</h2>
        {contactsQuery.isError ? (
          <p className="alert alert-error" role="alert">
            {problemMessage(contactsQuery.error)}
          </p>
        ) : contacts.length === 0 ? (
          <p className="muted">Esta cuenta no tiene contactos.</p>
        ) : (
          <ul>
            {contacts.map((contact) => (
              <li key={contact.id}>
                <Link to={`/app/contactos/${contact.id}`}>{contact.fullName}</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="stack" aria-labelledby="archivar-cuenta">
        <h2 id="archivar-cuenta">Archivar</h2>
        <Button variant="danger" onClick={() => archive.mutate()} loading={archive.isPending}>
          Archivar cuenta
        </Button>
      </section>
    </div>
  );
}
