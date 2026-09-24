import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { AuthPage } from "./AuthPage";
import { AuthProvider } from "./AuthProvider";


it("shows a server error without clearing form values", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "invalid_credentials",
          message: "Invalid email or password",
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <AuthProvider>
        <AuthPage mode="login" />
      </AuthProvider>
    </MemoryRouter>,
  );

  await user.type(screen.getByLabelText(/email/i), "person@example.com");
  await user.type(screen.getByLabelText(/password/i), "wrong-password");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByText("Invalid email or password")).toBeVisible();
  expect(screen.getByLabelText(/email/i)).toHaveValue("person@example.com");
});


it("renders accessible registration fields", () => {
  render(
    <MemoryRouter>
      <AuthProvider>
        <AuthPage mode="register" />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(screen.getByText("AiderAI")).toBeVisible();
  expect(screen.getByRole("heading", { name: /create your account/i })).toBeVisible();
  expect(screen.getByLabelText(/full name/i)).toBeVisible();
});
