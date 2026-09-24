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


function renderChat(entry = "/chat") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}><ChatPage /></MemoryRouter>
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

  await user.type(screen.getByLabelText(/message aiderai/i), "How long do refunds take?");
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

  await user.type(screen.getByLabelText(/message aiderai/i), "Please help");
  await user.click(screen.getByRole("button", { name: /send message/i }));

  expect(await screen.findByText("Please help")).toBeVisible();
  expect(screen.getByRole("button", { name: /retry/i })).toBeVisible();
  await user.click(screen.getByRole("button", { name: /retry/i }));
  expect(await screen.findByRole("button", { name: /retry/i })).toBeVisible();
  expect(screen.getAllByText("Please help")).toHaveLength(1);
});


it("loads a selected conversation and continues it", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: "c-existing",
      title: "Refund",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      messages: [{ id: "m1", role: "assistant", content: "Earlier answer", citations: [], created_at: "2026-01-01T00:00:00Z" }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }))
    .mockResolvedValueOnce(streamResponse([
      'event: token\ndata: {"text":"Continued"}\n\n',
      'event: complete\ndata: {"conversation_id":"c-existing"}\n\n',
    ]));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderChat("/chat?conversation=c-existing");

  expect(await screen.findByText("Earlier answer")).toBeVisible();
  await user.type(screen.getByLabelText(/message aiderai/i), "Follow up");
  await user.click(screen.getByRole("button", { name: /send message/i }));
  expect(await screen.findByText("Continued")).toBeVisible();
  const request = fetchMock.mock.calls[1][1] as RequestInit;
  expect(JSON.parse(String(request.body)).conversation_id).toBe("c-existing");
});
