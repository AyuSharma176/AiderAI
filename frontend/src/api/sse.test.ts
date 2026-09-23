import { SSEDecoder } from "./sse";


it("buffers split frames until a blank line arrives", () => {
  const decoder = new SSEDecoder();

  expect(decoder.push('event: token\ndata: {"te')).toEqual([]);
  expect(decoder.push('xt":"Hello"}\n')).toEqual([]);
  expect(decoder.push("\n")).toEqual([
    { event: "token", data: { text: "Hello" } },
  ]);
});


it("parses multiple events and CRLF framing", () => {
  const decoder = new SSEDecoder();

  expect(
    decoder.push(
      'event: stage\r\ndata: {"name":"retrieving"}\r\n\r\nevent: complete\ndata: {"conversation_id":"c1"}\n\n',
    ),
  ).toEqual([
    { event: "stage", data: { name: "retrieving" } },
    { event: "complete", data: { conversation_id: "c1" } },
  ]);
});
