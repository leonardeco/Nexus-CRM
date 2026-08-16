import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { Account, AccountPage, Contact, ContactPage } from "../../api/types";
import { Button } from "../../ui/Button";
import { SelectField, TextField, focusFirstInvalid } from "../../ui/Field";

const CONSENT_LABEL: Record<Contact["consentStatus"], string> = {
  unknown: "Sin registrar",
  granted: "Otorgado",
  denied: "Rechazado",
};

export function ContactsPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [formError, setFormError] = useState<string>();

  const contactsQuery = useQuery({
    queryKey: ["contacts", query],
    queryFn: () =>
      api<ContactPage>(`/contacts${query ? `?q=${encodeURIComponent(query)}` : ""}`),
  });

  const accountsQuery = useQuery({
    queryKey: ["accounts", "picker"],
    queryFn: () => api<AccountPage>("/accounts?limit=100"),
  });

  const create = useMutation({
    mutationFn: async (body: {
      fullName: string;
      primaryEmail?: string;
      accountId?: string;
    }) =>
      api<Contact>("/contacts", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: async () => {
      setFormError(undefined);
      await queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    const accountId = String(data.get("accountId") ?? "");
    const primaryEmail = String(data.get("primaryEmail") ?? "");
    create.mutate({
      fullName: String(data.get("fullName") ?? ""),
      primaryEmail: primaryEmail || undefined,
      accountId: accountId || undefined,
    });
    form.reset();
  }

  const accounts = accountsQuery.data?.items ?? [];
  const accountName = (id?: string | null): string => {
    if (!id) return "—";
    const found = accounts.find((a: Account) => a.id === id);
    return found ? found.name : "—";
  };

  return (
    <div className="stack-lg">
      <h1>Contactos</h1>
      {formError ? (
        <p className="alert alert-error" role="alert">
          {formError}
        </p>
      ) : null}

      <section className="stack" aria-labelledby="nuevo-contacto">
        <h2 id="nuevo-contacto">Nuevo contacto</h2>
        <form className="stack" onSubmit={onCreate} noValidate>
          <TextField name="fullName" label="Nombre completo" required autoComplete="name" />
          <TextField name="primaryEmail" type="email" label="Correo principal" autoComplete="email" />
          <SelectField name="accountId" label="Cuenta (opcional)">
            <option value="">Sin cuenta</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </SelectField>
          <Button type="submit" loading={create.isPending}>
            Crear contacto
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="buscar-contactos">
        <h2 id="buscar-contactos">Buscar</h2>
        <TextField
          name="q"
          label="Buscar por nombre o correo"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          autoComplete="off"
        />
      </section>

      {contactsQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(contactsQuery.error)}
        </p>
      ) : contactsQuery.isLoading ? (
        <p className="muted">Cargando…</p>
      ) : (contactsQuery.data?.items.length ?? 0) === 0 ? (
        <p className="muted">No hay contactos todavía.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="muted">Contactos de la empresa</caption>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Correo</th>
                <th>Cuenta</th>
                <th>Habeas data</th>
              </tr>
            </thead>
            <tbody>
              {contactsQuery.data?.items.map((contact) => (
                <tr key={contact.id}>
                  <td>
                    <Link to={`/app/contactos/${contact.id}`}>{contact.fullName}</Link>
                  </td>
                  <td>{contact.primaryEmail ?? "—"}</td>
                  <td>{accountName(contact.accountId)}</td>
                  <td>{CONSENT_LABEL[contact.consentStatus]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
