import { consumeEventStream } from "./http.js";

export function streamGraph(workspace, limit, onEvent) {
  const params = new URLSearchParams({
    workspace: (workspace || "docs").trim() || "docs",
    limit: String(limit),
  });
  return consumeEventStream(`/api/graph/stream?${params}`, {}, onEvent);
}
