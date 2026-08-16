import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type {
  Deal,
  DealHistory,
  DealStatus,
  PipelinePage,
} from "../../api/types";
import { Button } from "../../ui/Button";
import { SelectField, TextField, focusFirstInvalid } from "../../ui/Field";
import { formatCOP } from "./format";

const STATUS_LABEL: Record<DealStatus, string> = {
  open: "Abierto",
  won: "Ganado",
  lost: "Perdido",
};

export function DealDetailPage() {
  const { dealId = "" } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string>();
  const [status, setStatus] = useState<string>();

  const dealQuery = useQuery({
    queryKey: ["deal", dealId],
    queryFn: () => api<Deal>(`/deals/${dealId}`),
  });

  const pipelinesQuery = useQuery({
    queryKey: ["pipelines"],
    queryFn: () => api<PipelinePage>("/pipelines"),
  });

  const historyQuery = useQuery({
    queryKey: ["deal-history", dealId],
    queryFn: () => api<DealHistory>(`/deals/${dealId}/history`),
  });

  function invalidate() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ["deal", dealId] }),
      queryClient.invalidateQueries({ queryKey: ["deal-history", dealId] }),
      queryClient.invalidateQueries({ queryKey: ["board"] }),
    ]);
  }

  const update = useMutation({
    mutationFn: (changes: Partial<Deal>) =>
      api<Deal>(`/deals/${dealId}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      }),
    onSuccess: async () => {
      setStatus("Negocio actualizado.");
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const move = useMutation({
    mutationFn: (body: { toStageId: string; reason?: string }) =>
      api<Deal>(`/deals/${dealId}/stage`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setStatus("Etapa actualizada.");
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const changeStatus = useMutation({
    mutationFn: (body: { status: DealStatus; lostReason?: string }) =>
      api<Deal>(`/deals/${dealId}/status`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setStatus("Estado actualizado.");
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const archive = useMutation({
    mutationFn: () =>
      api<Deal>(`/deals/${dealId}/archive`, { method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["board"] });
      navigate("/app/pipeline");
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  if (dealQuery.isError) {
    return (
      <div className="stack-lg">
        <h1>Negocio</h1>
        <p className="alert alert-error" role="alert">
          {problemMessage(dealQuery.error)}
        </p>
        <Link to="/app/pipeline">Volver al pipeline</Link>
      </div>
    );
  }

  if (dealQuery.isLoading || !dealQuery.data) {
    return (
      <div className="stack-lg">
        <h1>Negocio</h1>
        <p className="muted">Cargando…</p>
      </div>
    );
  }

  const deal = dealQuery.data;
  const pipeline = pipelinesQuery.data?.items.find(
    (item) => item.id === deal.pipelineId,
  );
  const stages = pipeline?.stages ?? [];

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
      value: String(data.get("value") ?? "0"),
      closeDate: String(data.get("closeDate") ?? "") || null,
      probability: Number(data.get("probability") ?? 0),
    });
  }

  function onMove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const toStageId = String(data.get("toStageId") ?? "");
    if (!toStageId) return;
    move.mutate({
      toStageId,
      reason: String(data.get("reason") ?? "") || undefined,
    });
  }

  function onStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const nextStatus = String(data.get("status") ?? "open") as DealStatus;
    changeStatus.mutate({
      status: nextStatus,
      lostReason:
        nextStatus === "lost"
          ? String(data.get("lostReason") ?? "") || undefined
          : undefined,
    });
  }

  return (
    <div className="stack-lg">
      <p>
        <Link to="/app/pipeline">← Pipeline</Link>
      </p>
      <h1>{deal.name}</h1>
      <p className="muted">
        {formatCOP(deal.value)} · {STATUS_LABEL[deal.status]} ·{" "}
        {deal.daysInStage} días en etapa
        {deal.isRotting ? " · Estancado" : ""}
      </p>
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

      <section className="stack" aria-labelledby="datos-negocio">
        <h2 id="datos-negocio">Datos</h2>
        <form className="stack" onSubmit={onUpdate} noValidate>
          <TextField name="name" label="Nombre" required defaultValue={deal.name} />
          <TextField
            name="value"
            type="number"
            label="Valor (COP)"
            min={0}
            step="0.01"
            defaultValue={deal.value}
          />
          <TextField
            name="closeDate"
            type="date"
            label="Fecha de cierre"
            defaultValue={deal.closeDate ?? ""}
          />
          <TextField
            name="probability"
            type="number"
            label="Probabilidad (%)"
            min={0}
            max={100}
            defaultValue={deal.probability ?? 0}
          />
          <Button type="submit" loading={update.isPending}>
            Guardar cambios
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="mover-etapa">
        <h2 id="mover-etapa">Mover de etapa</h2>
        <form className="stack" onSubmit={onMove} noValidate>
          <SelectField name="toStageId" label="Etapa destino" defaultValue="">
            <option value="">Selecciona etapa…</option>
            {stages
              .filter((stage) => stage.id !== deal.stageId)
              .map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stage.name}
                </option>
              ))}
          </SelectField>
          <TextField name="reason" label="Motivo del cambio" />
          <Button type="submit" variant="secondary" loading={move.isPending}>
            Mover negocio
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="estado-negocio">
        <h2 id="estado-negocio">Estado</h2>
        <form className="stack" onSubmit={onStatus} noValidate>
          <SelectField name="status" label="Estado" defaultValue={deal.status}>
            <option value="open">Abierto</option>
            <option value="won">Ganado</option>
            <option value="lost">Perdido</option>
          </SelectField>
          <TextField
            name="lostReason"
            label="Motivo de pérdida"
            defaultValue={deal.lostReason ?? ""}
          />
          <Button type="submit" variant="secondary" loading={changeStatus.isPending}>
            Actualizar estado
          </Button>
        </form>
      </section>

      <section className="stack" aria-labelledby="historial">
        <h2 id="historial">Historial de etapas</h2>
        {historyQuery.isError ? (
          <p className="alert alert-error" role="alert">
            {problemMessage(historyQuery.error)}
          </p>
        ) : historyQuery.isLoading ? (
          <p className="muted">Cargando…</p>
        ) : (historyQuery.data?.items.length ?? 0) === 0 ? (
          <p className="muted">Sin movimientos.</p>
        ) : (
          <ul className="stack">
            {historyQuery.data?.items.map((event) => (
              <li key={event.id}>
                {event.fromStageName ?? "Inicio"} → {event.toStageName ?? "—"}
                {event.reason ? ` · ${event.reason}` : ""}
                <span className="muted"> · {event.occurredAt}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="stack" aria-labelledby="archivar-negocio">
        <h2 id="archivar-negocio">Archivar</h2>
        <Button variant="danger" onClick={() => archive.mutate()} loading={archive.isPending}>
          Archivar negocio
        </Button>
      </section>
    </div>
  );
}
