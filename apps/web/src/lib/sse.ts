/**
 * Minimal SSE reader on top of fetch + ReadableStream so we can send the
 * `Authorization` header (which the browser EventSource API does not allow).
 *
 * Yields parsed events; closes when the server sends `event: done`/`error`.
 */
import { useAuthStore } from "@/stores/auth-store";

export interface SseEvent {
  event: string;
  data: string;
}

export async function* readSse(
  url: string,
  { signal }: { signal?: AbortSignal } = {},
): AsyncGenerator<SseEvent> {
  const access = useAuthStore.getState().accessToken;
  const res = await fetch(url, {
    headers: {
      accept: "text/event-stream",
      ...(access ? { authorization: `Bearer ${access}` } : {}),
    },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`SSE connection failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    // Normalize CRLF → LF so block (\n\n) and line (\n) parsing works whether the
    // server emits "\n\n" or "\r\n\r\n" event separators.
    buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const raw of block.split("\n")) {
        const line = raw.trimStart();
        if (!line || line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length === 0) continue;
      yield { event, data: dataLines.join("\n") };
    }
  }
}
