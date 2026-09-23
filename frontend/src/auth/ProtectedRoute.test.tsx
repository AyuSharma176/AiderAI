import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./AuthProvider";
import { ProtectedRoute } from "./ProtectedRoute";


it("redirects anonymous users to login", () => {
  render(
    <MemoryRouter initialEntries={["/chat"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<h1>Welcome back</h1>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/chat" element={<h1>Chat</h1>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
});


it("renders protected content for an authenticated session", () => {
  sessionStorage.setItem("supportai.access_token", "test-token");

  render(
    <MemoryRouter initialEntries={["/chat"]}>
      <AuthProvider>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/chat" element={<h1>Support chat</h1>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: /support chat/i })).toBeVisible();
});
