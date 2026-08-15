import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test } from "vitest";
import { useAuthStore } from "../../stores/auth-store";
import { SignupPage } from "./SignupPage";

function renderSignup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SignupPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useAuthStore.setState({ principal: null, mfaChallengeId: null });
});

test("TC-2.4 consent checkboxes are explicit with policy links", () => {
  renderSignup();

  const privacy = screen.getByRole("checkbox", {
    name: "Acepto la política de privacidad",
  }) as HTMLInputElement;
  const habeas = screen.getByRole("checkbox", {
    name: "Acepto el tratamiento de datos personales (habeas data)",
  }) as HTMLInputElement;

  expect(privacy.required).toBe(true);
  expect(habeas.required).toBe(true);

  const privacyLabel = privacy.closest("label");
  const habeasLabel = habeas.closest("label");
  expect(privacyLabel?.querySelector("a")).toBeNull();
  expect(habeasLabel?.querySelector("a")).toBeNull();
  expect(screen.getByRole("link", { name: "política de privacidad" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "habeas data" })).toBeTruthy();
});
