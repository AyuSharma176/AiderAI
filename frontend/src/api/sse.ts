export interface SSEEvent<T = Record<string, unknown>> {
  event: string;
  data: T;
}

export class SSEDecoder {
  private buffer = "";

  push(chunk: string): SSEEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const frames = this.buffer.split("\n\n");
    this.buffer = frames.pop() ?? "";
    return frames.flatMap((frame) => {
      let event = "message";
      const data: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!data.length) return [];
      return [{ event, data: JSON.parse(data.join("\n")) as Record<string, unknown> }];
    });
  }
}

export async function consumeSSE(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const reader = stream.getReader();
  const textDecoder = new TextDecoder();
  const decoder = new SSEDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const event of decoder.push(textDecoder.decode(value, { stream: true }))) {
        onEvent(event);
      }
    }
  } finally {
    reader.releaseLock();
  }
}
