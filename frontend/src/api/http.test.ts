import { authenticatedFetch } from "./http";


it("includes browser credentials on API requests", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(null, { status: 204 }));

  await authenticatedFetch("/integrations/gmail");

  expect(fetchMock).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({ credentials: "include" }),
  );
});
