import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test } from "vitest";
import { useAuthStore } from "../../stores/auth-store";
import { PublicArcoPage } from "./PublicArcoPage";

function renderPublicArco() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/t/acme/arco"]}>
        <Routes>
          <Route path="/t/:slug/arco" element={<PublicArcoPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useAuthStore.setState({ principal: null, mfaChallengeId: null });
});

test("public ARCO select lists acceso, rectificación, cancelación and oposición", () => {
  renderPublicArco();

  const select = screen.getByRole("combobox");
  const labels = within(select)
    .getAllByRole("option")
    .map((option) => option.textContent?.trim());

  expect(labels).toEqual(
    expect.arrayContaining([
      "acceso",
      "rectificación",
      "cancelación",
      "oposición",
    ]),
  );
});
