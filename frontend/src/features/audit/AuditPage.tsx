import { useQuery } from "@tanstack/react-query";
import { api, problemMessage } from "../../api/client";
import type { AuditPage } from "../../api/types";

export function AuditPage() {
  const auditQuery = useQuery({
    queryKey: ["audit-events"],
    queryFn: () => api<AuditPage>("/audit-events"),
  });

  const items = auditQuery.data?.items ?? [];

  return (
    <div className="stack-lg">
      <h1>Auditoría</h1>
      {auditQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(auditQuery.error)}
        </p>
      ) : null}
      <div className="table-wrap">
        <table>
          <caption className="muted">Eventos inmutables</caption>
          <thead>
            <tr>
              <th>Cuándo</th>
              <th>Quién</th>
              <th>Qué</th>
              <th>Desde dónde</th>
            </tr>
          </thead>
          <tbody>
            {items.map((event) => (
              <tr key={event.id}>
                <td>{new Date(event.occurredAt).toLocaleString("es-CO")}</td>
                <td>{event.actorEmail ?? "—"}</td>
                <td>{event.eventType}</td>
                <td>{event.ipAddress ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
