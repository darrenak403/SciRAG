import { API_BASE, ApiError, errorFrom } from "@/lib/api-client";

export type ServerEvent = { event: string; data: unknown };

/** Splits what has arrived so far into whole events and the unfinished rest. */
export function parseEvents(buffer: string): { events: ServerEvent[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  const events: ServerEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) continue;
    try {
      events.push({ event, data: JSON.parse(data.join("\n")) });
    } catch {
      // A block that is not JSON is not one of ours; skip it.
    }
  }
  return { events, rest };
}

/**
 * POSTs `json` and yields the events of the answer as they arrive. The browser's
 * EventSource cannot be used: it only sends GET. Aborting `signal` ends the stream.
 */
export async function* postEvents(
  path: string,
  json: unknown,
  signal: AbortSignal,
): AsyncGenerator<ServerEvent> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(json),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError(0, "Couldn't reach the server. Check your connection and try again.", "network");
  }
  if (!response.ok || !response.body) {
    if (response.status === 401) window.location.assign("/login");
    throw errorFrom(response.status, await response.json().catch(() => null));
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += value;
      const { events, rest } = parseEvents(buffer);
      buffer = rest;
      yield* events;
    }
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError(0, "The connection was lost before the answer finished.", "network");
  } finally {
    reader.cancel().catch(() => {});
  }
}
