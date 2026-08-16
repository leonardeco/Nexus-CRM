import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, problemMessage } from "../../api/client";
import type { Forecast, PipelinePage } from "../../api/types";
import { SelectField } from "../../ui/Field";
import { formatCOP } from "./format";

export function ForecastPage() {
  const [selectedId, setSelectedId] = useState("");

  const pipelinesQuery = useQuery({
    queryKey: ["pipelines"],
    queryFn: () => api<PipelinePage>("/pipelines"),
  });

  const pipelines = pipelinesQuery.data?.items ?? [];
  const pipelineId = selectedId || pipelines[0]?.id || "";

  const forecastQuery = useQuery({
    queryKey: ["forecast", pipelineId],
    queryFn: () => api<Forecast>(`/pipelines/${pipelineId}/forecast`),
    enabled: Boolean(pipelineId),
  });

  const forecast = forecastQuery.data;

  return (
    <div className="stack-lg">
      <h1>Forecast</h1>

      <section className="stack" aria-labelledby="seleccionar-forecast">
        <h2 id="seleccionar-forecast">Embudo</h2>
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

      {pipelinesQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(pipelinesQuery.error)}
        </p>
      ) : forecastQuery.isError ? (
        <p className="alert alert-error" role="alert">
          {problemMessage(forecastQuery.error)}
        </p>
      ) : forecastQuery.isLoading || pipelinesQuery.isLoading ? (
        <p className="muted">Cargando…</p>
      ) : !forecast ? (
        <p className="muted">No hay datos de forecast.</p>
      ) : (
        <>
          <section className="stack" aria-labelledby="forecast-etapas">
            <h2 id="forecast-etapas">Proyección por etapa</h2>
            <div className="table-wrap">
              <table>
                <caption className="muted">
                  Valor ponderado = valor × probabilidad
                </caption>
                <thead>
                  <tr>
                    <th>Etapa</th>
                    <th>Negocios</th>
                    <th>Valor</th>
                    <th>Ponderado</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.stages.map((stage) => (
                    <tr key={stage.stageId}>
                      <td>{stage.name}</td>
                      <td>{stage.count}</td>
                      <td>{formatCOP(stage.sum)}</td>
                      <td>{formatCOP(stage.weighted)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">Totales</th>
                    <td>{forecast.totals.count}</td>
                    <td>{formatCOP(forecast.totals.sum)}</td>
                    <td>{formatCOP(forecast.totals.weighted)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </section>

          <section className="stack" aria-labelledby="forecast-meses">
            <h2 id="forecast-meses">Proyección mensual</h2>
            {forecast.months.length === 0 ? (
              <p className="muted">Sin fechas de cierre registradas.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <caption className="muted">
                    Agrupado por mes de cierre
                  </caption>
                  <thead>
                    <tr>
                      <th>Mes</th>
                      <th>Valor</th>
                      <th>Ponderado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.months.map((month) => (
                      <tr key={month.month}>
                        <td>{month.month}</td>
                        <td>{formatCOP(month.sum)}</td>
                        <td>{formatCOP(month.weighted)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
