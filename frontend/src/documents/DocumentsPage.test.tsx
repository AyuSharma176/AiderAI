import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { DocumentsPage } from "./DocumentsPage";
import { pollingInterval } from "./useDocuments";


function renderDocuments() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><DocumentsPage /></QueryClientProvider>);
}


it("rejects a non-PDF before upload", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup({ applyAccept: false });
  renderDocuments();

  const input = screen.getByLabelText(/upload pdf/i);
  await user.upload(input, new File(["text"], "notes.txt", { type: "text/plain" }));

  expect(screen.getByText("Choose a PDF file.")).toBeVisible();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});


it("polls only while a document is pending or processing", () => {
  expect(pollingInterval([{ status: "pending" }])).toBe(3000);
  expect(pollingInterval([{ status: "processing" }])).toBe(3000);
  expect(pollingInterval([{ status: "ready" }])).toBe(false);
});


it("renders a safe failed status message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([{ id: "d1", filename: "broken.pdf", status: "failed", error_message: "Document processing failed. Please try again.", created_at: "2026-09-23T10:00:00Z", updated_at: "2026-09-23T10:00:00Z" }]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );
  renderDocuments();

  expect(await screen.findByText("broken.pdf")).toBeVisible();
  expect(screen.getByText("Document processing failed. Please try again.")).toBeVisible();
});
