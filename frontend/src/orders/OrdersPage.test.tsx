import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { OrderDetailPage } from "./OrderDetailPage";
import { OrdersPage } from "./OrdersPage";


const order = {
  id: "11111111-1111-4111-8111-111111111111",
  marketplace: "amazon",
  marketplace_order_id: "A-1",
  status: "shipped",
  placed_at: "2026-09-20T10:00:00Z",
  currency: "INR",
  total_amount: "1299.00",
  expected_delivery_at: null,
  delivered_at: null,
  tracking_number: "TRACK-1",
  carrier: "ATS",
  marketplace_url: null,
  last_source_message_at: "2026-09-21T10:00:00Z",
  items: [{ id: "i1", title: "USB-C charger", quantity: 1, unit_price: null, marketplace_product_id: null }],
  events: [],
};

function wrapper(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}


it("filters unified orders and shows sync freshness", async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(
    JSON.stringify({ items: [order], next_cursor: null, last_sync_completed_at: "2026-09-24T10:00:00Z" }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  )));
  vi.stubGlobal("fetch", fetchMock);
  render(wrapper(<MemoryRouter><OrdersPage userId="user-1" /></MemoryRouter>));

  expect(await screen.findByText("USB-C charger")).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText(/marketplace/i), "flipkart");

  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
    expect.stringContaining("marketplace=flipkart"), expect.anything(),
  ));
  expect(screen.getByText(/last synced/i)).toBeVisible();
});


it("does not render a non-allow-listed marketplace link", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(order), {
    status: 200, headers: { "Content-Type": "application/json" },
  })));
  render(wrapper(
    <MemoryRouter initialEntries={[`/orders/${order.id}`]}>
      <Routes><Route path="/orders/:orderId" element={<OrderDetailPage userId="user-1" />} /></Routes>
    </MemoryRouter>,
  ));

  expect(await screen.findByText(order.marketplace_order_id)).toBeVisible();
  expect(screen.queryByRole("link", { name: /open in/i })).not.toBeInTheDocument();
});
