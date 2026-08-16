import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ContactsPage } from "./ContactsPage";

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
      if (url.includes("/accounts")) {
        return jsonResponse({ items: [] });
      }
      return jsonResponse({ items: [] });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderContacts() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/app/contactos"]}>
        <Routes>
          <Route path="/app/contactos" element={<ContactsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("contacts page shows heading, create form and empty state", async () => {
  renderContacts();

  expect(
    screen.getByRole("heading", { level: 1, name: "Contactos" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Crear contacto" }),
  ).toBeTruthy();
  await waitFor(() =>
    expect(screen.getByText("No hay contactos todavía.")).toBeTruthy(),
  );
});
