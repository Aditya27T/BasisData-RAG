import { consumeEventStream } from "./http.js";

export function streamChat(question, workspace, onEvent) {
  return consumeEventStream("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, workspace: (workspace || "docs").trim() || "docs" }),
  }, onEvent);
}
