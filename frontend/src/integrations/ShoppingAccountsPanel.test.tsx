import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ShoppingAccountsPanel } from "./ShoppingAccountsPanel";


function renderPanel(navigate = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ShoppingAccountsPanel userId="user-1" navigate={navigate} />
    </QueryClientProvider>,
  );
  return navigate;
}


it("starts Gmail authorization from Knowledge Base", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "disconnected", marketplace_counts: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=safe",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
  vi.stubGlobal("fetch", fetchMock);
  const navigate = renderPanel();

  await userEvent.click(await screen.findByRole("button", { name: /connect gmail/i }));

  expect(navigate).toHaveBeenCalledWith(
    "https://accounts.google.com/o/oauth2/v2/auth?state=safe",
  );
});


it("shows freshness, counts, and reconnect state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "reconnect_required",
          email_address: "orders@example.com",
          last_sync_completed_at: "2026-09-24T10:00:00Z",
          imported_order_count: 6,
          marketplace_counts: { amazon: 4, flipkart: 2 },
          reconnect_required: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );
  renderPanel();

  expect(await screen.findByText(/reconnect required/i)).toBeVisible();
  expect(screen.getByText("4 Amazon orders")).toBeVisible();
  expect(screen.getByText("2 Flipkart orders")).toBeVisible();
  expect(screen.getByText(/last synced/i)).toBeVisible();
});
