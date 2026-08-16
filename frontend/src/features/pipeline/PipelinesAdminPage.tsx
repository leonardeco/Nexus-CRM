import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, problemMessage } from "../../api/client";
import type { Pipeline, PipelinePage, Stage } from "../../api/types";
import { Button } from "../../ui/Button";
import { TextField, focusFirstInvalid } from "../../ui/Field";

export function PipelinesAdminPage() {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string>();

  const pipelinesQuery = useQuery({
    queryKey: ["pipelines"],
    queryFn: () => api<PipelinePage>("/pipelines"),
  });

  function invalidate() {
    return queryClient.invalidateQueries({ queryKey: ["pipelines"] });
  }

  const createPipeline = useMutation({
    mutationFn: (body: { name: string; isDefault: boolean }) =>
      api<Pipeline>("/pipelines", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: async () => {
      setFormError(undefined);
      await invalidate();
    },
    onError: (error) => setFormError(problemMessage(error)),
  });

  const setDefault = useMutation({
    mutationFn: (pipelineId: string) =>
      api<Pipeline>(`/pipelines/${pipelineId}`, {
        method: "PATCH",
        body: JSON.stringify({ isDefault: true }),
      }),
    onSuccess: () => invalidate(),
    onError: (error) => setFormError(problemMessage(error)),
  });

  function onCreatePipeline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    createPipeline.mutate({
      name: String(data.get("name") ?? ""),
      isDefault: data.get("isDefault") === "on",
    });
    form.reset();
  }

  const pipelines = pipelinesQuery.data?.items ?? [];

  return (
    <div className="stack-lg">
      <h1>Pipelines</h1>
      {formError ? (
        <p className="alert alert-error" role="alert">
          {formError}
        </p>
      ) : null}

      <section className="stack" aria-labelledby="nuevo-pipeline">
        <h2 id="nuevo-pipeline">Nuevo pipeline</h2>
        <form className="stack" onSubmit={onCreatePipeline} noValidate>
          <TextField name="name" label="Nombre" required />
          <label className="field-inline">
            <input type="checkbox" name="isDefault" /> Predeterminado
          </label>
          <Button type="submit" loading={createPipeline.isPending}>
            Crear pipeline
          </Button>
        </form>
      </section>

      {pipelinesQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(pipelinesQuery.error)}
        </p>
      ) : pipelinesQuery.isLoading ? (
        <p className="muted">Cargando…</p>
      ) : pipelines.length === 0 ? (
        <p className="muted">No hay pipelines todavía.</p>
      ) : (
        pipelines.map((pipeline) => (
          <PipelineAdminCard
            key={pipeline.id}
            pipeline={pipeline}
            onDefault={() => setDefault.mutate(pipeline.id)}
            onError={setFormError}
            invalidate={invalidate}
          />
        ))
      )}
    </div>
  );
}

function PipelineAdminCard({
  pipeline,
  onDefault,
  onError,
  invalidate,
}: {
  pipeline: Pipeline;
  onDefault: () => void;
  onError: (message: string) => void;
  invalidate: () => Promise<unknown>;
}) {
  const addStage = useMutation({
    mutationFn: (body: {
      name: string;
      probability: number;
      rottingDays?: number;
    }) =>
      api<Stage>(`/pipelines/${pipeline.id}/stages`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidate(),
    onError: (error) => onError(problemMessage(error)),
  });

  const reorder = useMutation({
    mutationFn: (stageIds: string[]) =>
      api<Pipeline>(`/pipelines/${pipeline.id}/stages/reorder`, {
        method: "POST",
        body: JSON.stringify({ stageIds }),
      }),
    onSuccess: () => invalidate(),
    onError: (error) => onError(problemMessage(error)),
  });

  function move(index: number, delta: number) {
    const ids = pipeline.stages.map((stage) => stage.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate(ids);
  }

  function onAddStage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) {
      focusFirstInvalid(form);
      return;
    }
    const data = new FormData(form);
    const rotting = String(data.get("rottingDays") ?? "");
    addStage.mutate({
      name: String(data.get("name") ?? ""),
      probability: Number(data.get("probability") ?? 0),
      rottingDays: rotting ? Number(rotting) : undefined,
    });
    form.reset();
  }

  return (
    <section className="stack card" aria-label={pipeline.name}>
      <h2>
        {pipeline.name}
        {pipeline.isDefault ? " · Predeterminado" : ""}
      </h2>
      {!pipeline.isDefault ? (
        <Button variant="secondary" onClick={onDefault}>
          Marcar como predeterminado
        </Button>
      ) : null}

      <div className="table-wrap">
        <table>
          <caption className="muted">Etapas de {pipeline.name}</caption>
          <thead>
            <tr>
              <th>Orden</th>
              <th>Etapa</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {pipeline.stages.map((stage, index) => (
              <StageRow
                key={stage.id}
                stage={stage}
                index={index}
                total={pipeline.stages.length}
                onMoveUp={() => move(index, -1)}
                onMoveDown={() => move(index, 1)}
                onError={onError}
                invalidate={invalidate}
              />
            ))}
          </tbody>
        </table>
      </div>

      <form className="stack" onSubmit={onAddStage} noValidate>
        <h3>Agregar etapa</h3>
        <TextField name="name" label="Nombre" required />
        <TextField
          name="probability"
          type="number"
          label="Probabilidad (%)"
          min={0}
          max={100}
          defaultValue={0}
        />
        <TextField name="rottingDays" type="number" label="Días para estancarse" min={1} />
        <Button type="submit" loading={addStage.isPending}>
          Agregar etapa
        </Button>
      </form>
    </section>
  );
}

function StageRow({
  stage,
  index,
  total,
  onMoveUp,
  onMoveDown,
  onError,
  invalidate,
}: {
  stage: Stage;
  index: number;
  total: number;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onError: (message: string) => void;
  invalidate: () => Promise<unknown>;
}) {
  const update = useMutation({
    mutationFn: (body: {
      name: string;
      probability: number;
      rottingDays: number | null;
    }) =>
      api<Stage>(`/stages/${stage.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidate(),
    onError: (error) => onError(problemMessage(error)),
  });

  const remove = useMutation({
    mutationFn: () => api<void>(`/stages/${stage.id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(),
    onError: (error) => onError(problemMessage(error)),
  });

  function onSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const rotting = String(data.get("rottingDays") ?? "");
    update.mutate({
      name: String(data.get("name") ?? ""),
      probability: Number(data.get("probability") ?? 0),
      rottingDays: rotting ? Number(rotting) : null,
    });
  }

  return (
    <tr>
      <td>
        <div className="row">
          <Button
            variant="ghost"
            aria-label={`Subir ${stage.name}`}
            disabled={index === 0}
            onClick={onMoveUp}
          >
            ↑
          </Button>
          <Button
            variant="ghost"
            aria-label={`Bajar ${stage.name}`}
            disabled={index === total - 1}
            onClick={onMoveDown}
          >
            ↓
          </Button>
        </div>
      </td>
      <td>
        <form className="row" onSubmit={onSave} noValidate>
          <TextField name="name" label="Nombre" defaultValue={stage.name} required />
          <TextField
            name="probability"
            type="number"
            label="Prob. (%)"
            min={0}
            max={100}
            defaultValue={stage.probability}
          />
          <TextField
            name="rottingDays"
            type="number"
            label="Días"
            min={1}
            defaultValue={stage.rottingDays ?? ""}
          />
          <Button type="submit" variant="secondary" loading={update.isPending}>
            Guardar
          </Button>
        </form>
      </td>
      <td>
        <Button variant="danger" onClick={() => remove.mutate()} loading={remove.isPending}>
          Eliminar
        </Button>
      </td>
    </tr>
  );
}
