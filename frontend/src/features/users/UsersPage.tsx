import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, problemMessage } from "../../api/client";
import type { Role, User } from "../../api/types";
import { Button } from "../../ui/Button";
import { SelectField, TextField, focusFirstInvalid } from "../../ui/Field";

const ROLES: { value: Role; label: string }[] = [
  { value: "administrador", label: "Administrador" },
  { value: "gerente", label: "Gerente" },
  { value: "vendedor", label: "Vendedor" },
];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string>();
  const [status, setStatus] = useState<string>();

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });

  const invite = useMutation({
    mutationFn: async (body: { email: string; role: Role; fullName: string }) =>
      api<void>("/invites", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setStatus("Invitación enviada.");
      setFormError(undefined);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const deactivate = useMutation({
    mutationFn: async (userId: string) =>
      api<User>(`/users/${userId}/deactivation`, { method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const changeRole = useMutation({
    mutationFn: async (input: { userId: string; role: Role }) =>
      api<User>(`/users/${input.userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: input.role }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    invite.mutate({
      email: String(data.get("email") ?? ""),
      role: String(data.get("role") ?? "") as Role,
      fullName: String(data.get("fullName") ?? ""),
    });
    form.reset();
  }

  const users = usersQuery.data ?? [];

  return (
    <div className="stack-lg">
      <h1>Usuarios</h1>
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
      <section className="stack" aria-labelledby="invitar">
        <h2 id="invitar">Invitar</h2>
        <form className="stack" onSubmit={onInvite} noValidate>
          <TextField name="fullName" label="Nombre completo" required autoComplete="name" />
          <TextField name="email" type="email" label="Correo electrónico" required autoComplete="email" />
          <SelectField name="role" label="Rol" required>
            <option value="">Selecciona un rol</option>
            {ROLES.map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </SelectField>
          <Button type="submit" loading={invite.isPending}>
            Invitar
          </Button>
        </form>
      </section>
      <div className="table-wrap">
        <table>
          <caption className="muted">Personas de la empresa</caption>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Rol</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.fullName}</td>
                <td>{user.email}</td>
                <td>
                  <label className="sr-only" htmlFor={`role-${user.id}`}>
                    Rol de {user.fullName}
                  </label>
                  <select
                    id={`role-${user.id}`}
                    className="select"
                    value={user.role}
                    disabled={user.status !== "active"}
                    onChange={(event) =>
                      changeRole.mutate({
                        userId: user.id,
                        role: event.currentTarget.value as Role,
                      })
                    }
                  >
                    {ROLES.map((role) => (
                      <option key={role.value} value={role.value}>
                        {role.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{user.status}</td>
                <td>
                  {user.status === "active" ? (
                    <Button
                      variant="danger"
                      onClick={() => deactivate.mutate(user.id)}
                      loading={deactivate.isPending}
                    >
                      Desactivar
                    </Button>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
