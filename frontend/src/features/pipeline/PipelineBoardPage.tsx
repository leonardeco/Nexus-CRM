import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, problemMessage } from "../../api/client";
import type { Board, Deal, PipelinePage, Stage } from "../../api/types";
import { Button } from "../../ui/Button";
import { SelectField, TextField, focusFirstInvalid } from "../../ui/Field";
import { formatCOP } from "./format";

export function PipelineBoardPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState("");
  const [formError, setFormError] = useState<string>();

  const pipelinesQuery = useQuery({
    queryKey: ["pipelines"],
    queryFn: () => api<PipelinePage>("/pipelines"),
  });

  const pipelines = pipelinesQuery.data?.items ?? [];
  const pipelineId = selectedId || pipelines[0]?.id || "";

  const boardQuery = useQuery({
    queryKey: ["board", pipelineId],
    queryFn: () => api<Board>(`/pipelines/${pipelineId}/board`),
    enabled: Boolean(pipelineId),
  });

  const stages: Stage[] = useMemo(
    () => pipelines.find((p) => p.id === pipelineId)?.stages ?? [],
    [pipelines, pipelineId],
  );

  const create = useMutation({
    mutationFn: (body: {
      name: string;
      pipelineId: string;
      stageId?: string;
      value?: string;
      closeDate?: string;
    }) => api<Deal>("/deals", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: async () => {
      setFormError(undefined);
      await queryClient.invalidateQueries({ queryKey: ["board"] });
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
      pipelineId,
      stageId: String(data.get("stageId") ?? "") || undefined,
      value: String(data.get("value") ?? "") || undefined,
      closeDate: String(data.get("closeDate") ?? "") || undefined,
    });
    form.reset();
  }

  return (
    <div className="stack-lg">
      <h1>Pipeline</h1>
      {formError ? (
        <p className="alert alert-error" role="alert">
          {formError}
        </p>
      ) : null}

      <section className="stack" aria-labelledby="seleccionar-pipeline">
        <h2 id="seleccionar-pipeline">Embudo</h2>
        <SelectField
          name="pipelineId"
          label="Pipeline"
          value={pipelineId}
          onChange={(event) => setSelectedId(event.currentTarget.value)}
        >
          {pipelines.map((pipeline) => (
            <option key={pipeline.id} value={pipeline.id}>
              {pipeline.name}
              {pipeline.isDefault ? " (predeterminado)" : ""}
            </option>
          ))}
        </SelectField>
      </section>

      <section className="stack" aria-labelledby="nuevo-negocio">
        <h2 id="nuevo-negocio">Nuevo negocio</h2>
        <form className="stack" onSubmit={onCreate} noValidate>
          <TextField name="name" label="Nombre del negocio" required />
          <TextField name="value" type="number" label="Valor (COP)" min={0} step="0.01" />
          <TextField name="closeDate" type="date" label="Fecha de cierre" />
          <SelectField name="stageId" label="Etapa inicial (opcional)">
            <option value="">Primera etapa</option>
            {stages.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.name}
              </option>
            ))}
          </SelectField>
          <Button type="submit" loading={create.isPending} disabled={!pipelineId}>
            Crear negocio
          </Button>
        </form>
      </section>

      {pipelinesQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(pipelinesQuery.error)}
        </p>
      ) : boardQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(boardQuery.error)}
        </p>
      ) : boardQuery.isLoading || pipelinesQuery.isLoading ? (
        <p className="muted">Cargando…</p>
      ) : (
        <div className="board">
          {(boardQuery.data?.stages ?? []).map((column) => (
            <section
              key={column.stage.id}
              className="board-column stack"
              aria-label={column.stage.name}
            >
              <h2 className="board-column-title">
                {column.stage.name}
                <span className="muted"> · {column.stage.probability}%</span>
              </h2>
              {column.deals.length === 0 ? (
                <p className="muted">Sin negocios.</p>
              ) : (
                column.deals.map((deal) => (
                  <DealCard
                    key={deal.id}
                    deal={deal}
                    stages={boardQuery.data?.stages.map((c) => c.stage) ?? []}
                    onMoved={() =>
                      queryClient.invalidateQueries({ queryKey: ["board"] })
                    }
                  />
                ))
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function DealCard({
  deal,
  stages,
  onMoved,
}: {
  deal: Deal;
  stages: Stage[];
  onMoved: () => void;
}) {
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();

  const move = useMutation({
    mutationFn: (body: { toStageId: string; reason?: string }) =>
      api<Deal>(`/deals/${deal.id}/stage`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      setError(undefined);
      setTarget("");
      setReason("");
      onMoved();
    },
    onError: (mutationError) => setError(problemMessage(mutationError)),
  });

  const others = stages.filter((stage) => stage.id !== deal.stageId);

  return (
    <article className="deal-card stack">
      <p className="deal-card-name">
        <Link to={`/app/pipeline/${deal.id}`}>{deal.name}</Link>
      </p>
      <p className="deal-card-value">{formatCOP(deal.value)}</p>
      <p className="muted">
        Responsable: {deal.ownerUserId ? deal.ownerUserId : "Sin asignar"}
      </p>
      {deal.isRotting ? (
        <p className="badge badge-rotting" role="status">
          Estancado ({deal.daysInStage} días)
        </p>
      ) : null}
      {error ? (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      ) : null}
      <SelectField
        name={`move-${deal.id}`}
        label="Mover a"
        value={target}
        onChange={(event) => setTarget(event.currentTarget.value)}
      >
        <option value="">Selecciona etapa…</option>
        {others.map((stage) => (
          <option key={stage.id} value={stage.id}>
            {stage.name}
          </option>
        ))}
      </SelectField>
      <TextField
        name={`reason-${deal.id}`}
        label="Motivo"
        value={reason}
        onChange={(event) => setReason(event.currentTarget.value)}
      />
      <Button
        variant="secondary"
        loading={move.isPending}
        disabled={!target}
        onClick={() =>
          move.mutate({ toStageId: target, reason: reason || undefined })
        }
      >
        Mover
      </Button>
    </article>
  );
}
