import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { Account, AccountPage } from "../../api/types";
import { Button } from "../../ui/Button";
import { TextField, focusFirstInvalid } from "../../ui/Field";

export function AccountsPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [formError, setFormError] = useState<string>();

  const accountsQuery = useQuery({
    queryKey: ["accounts", query],
    queryFn: () =>
      api<AccountPage>(`/accounts${query ? `?q=${encodeURIComponent(query)}` : ""}`),
  });

  const create = useMutation({
    mutationFn: async (body: {
      name: string;
      industry?: string;
      region?: string;
      website?: string;
      phone?: string;
    }) => api<Account>("/accounts", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: async () => {
      setFormError(undefined);
      await queryClient.invalidateQueries({ queryKey: ["accounts"] });
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
    create.mutate({
      name: String(data.get("name") ?? ""),
      industry: String(data.get("industry") ?? "") || undefined,
      region: String(data.get("region") ?? "") || undefined,
      website: String(data.get("website") ?? "") || undefined,
      phone: String(data.get("phone") ?? "") || undefined,
    });
    form.reset();
  }

  return (
    <div className="stack-lg">
      <h1>Cuentas</h1>
      {formError ? (
        <p className="alert alert-error" role="alert">
          {formError}
        </p>
      ) : null}

      <section className="stack" aria-labelledby="nueva-cuenta">
        <h2 id="nueva-cuenta">Nueva cuenta</h2>
        <form className="stack" onSubmit={onCreate} noValidate>
          <TextField name="name" label="Nombre" required autoComplete="organization" />
          <TextField name="industry" label="Industria" />
          <TextField name="region" label="Región" />
          <TextField name="website" label="Sitio web" />
          <TextField name="phone" label="Teléfono" />
          <Button type="submit" loading={create.isPending}>
            Crear cuenta
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="buscar-cuentas">
        <h2 id="buscar-cuentas">Buscar</h2>
        <TextField
          name="q"
          label="Buscar por nombre"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          autoComplete="off"
        />
      </section>

      {accountsQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(accountsQuery.error)}
        </p>
      ) : accountsQuery.isLoading ? (
        <p className="muted">Cargando…</p>
      ) : (accountsQuery.data?.items.length ?? 0) === 0 ? (
        <p className="muted">No hay cuentas todavía.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <caption className="muted">Cuentas de la empresa</caption>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Industria</th>
                <th>Región</th>
              </tr>
            </thead>
            <tbody>
              {accountsQuery.data?.items.map((account) => (
                <tr key={account.id}>
                  <td>
                    <Link to={`/app/cuentas/${account.id}`}>{account.name}</Link>
                  </td>
                  <td>{account.industry ?? "—"}</td>
                  <td>{account.region ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
