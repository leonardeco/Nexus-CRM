import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { PipelineBoardPage } from "./PipelineBoardPage";

const STAGE = {
  id: "s1",
  pipelineId: "p1",
  name: "Prospecto",
  position: 1,
  probability: 10,
  rottingDays: 14,
  createdAt: "2026-08-15T00:00:00Z",
  updatedAt: "2026-08-15T00:00:00Z",
};

const PIPELINE = {
  id: "p1",
  name: "Ventas",
  isDefault: true,
  createdAt: "2026-08-15T00:00:00Z",
  updatedAt: "2026-08-15T00:00:00Z",
  stages: [STAGE],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/board")) {
        return jsonResponse({
          pipeline: PIPELINE,
          stages: [{ stage: STAGE, deals: [] }],
        });
      }
      if (url.includes("/pipelines")) {
        return jsonResponse({ items: [PIPELINE] });
      }
      return jsonResponse({ items: [] });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderBoard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/app/pipeline"]}>
        <Routes>
          <Route path="/app/pipeline" element={<PipelineBoardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("pipeline board renders heading, selector, create control and empty state", async () => {
  renderBoard();

  expect(
    screen.getByRole("heading", { level: 1, name: "Pipeline" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("heading", { level: 2, name: "Nuevo negocio" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Crear negocio" }),
  ).toBeTruthy();
  expect(screen.getByRole("combobox", { name: "Pipeline" })).toBeTruthy();
  await waitFor(() =>
    expect(screen.getByText("Sin negocios.")).toBeTruthy(),
  );
});
