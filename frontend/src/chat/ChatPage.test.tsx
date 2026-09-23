import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ChatPage } from "./ChatPage";


function streamResponse(frames: string[]) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}


function renderChat() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><ChatPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}


it("renders stage then streamed answer and citation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      streamResponse([
        'event: stage\ndata: {"name":"retrieving"}\n\n',
        'event: token\ndata: {"text":"Refunds "}\n\n',
        'event: token\ndata: {"text":"take five days."}\n\n',
        'event: citation\ndata: {"source":"refund.pdf","page":2}\n\n',
        'event: complete\ndata: {"conversation_id":"c1"}\n\n',
      ]),
    ),
  );
  const user = userEvent.setup();
  renderChat();

  await user.type(screen.getByLabelText(/message supportai/i), "How long do refunds take?");
  await user.click(screen.getByRole("button", { name: /send message/i }));

  expect(await screen.findByText("Refunds take five days.")).toBeVisible();
  expect(screen.getByText("refund.pdf · page 2")).toBeVisible();
  expect(screen.getByText(/searched knowledge base/i)).toBeVisible();
});


it("preserves a failed message and offers retry", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      streamResponse([
        'event: error\ndata: {"code":"ai_unavailable","message":"AI service is unavailable"}\n\n',
      ]),
    ),
  );
  const user = userEvent.setup();
  renderChat();

  await user.type(screen.getByLabelText(/message supportai/i), "Please help");
  await user.click(screen.getByRole("button", { name: /send message/i }));

  expect(await screen.findByText("Please help")).toBeVisible();
  expect(screen.getByRole("button", { name: /retry/i })).toBeVisible();
});
