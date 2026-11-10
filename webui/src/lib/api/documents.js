import { consumeEventStream, requestJson } from "./http.js";

function workspaceParam(workspace) {
  return encodeURIComponent((workspace || "docs").trim() || "docs");
}

export function listDocuments(workspace) {
  return requestJson(`/api/documents?workspace=${workspaceParam(workspace)}`);
}

export function startIngestion(file, workspace, force = false) {
  const form = new FormData();
  form.set("file", file);
  return requestJson(
    `/api/ingestions?workspace=${workspaceParam(workspace)}&force=${force}`,
    { method: "POST", body: form },
  );
}

export function streamIngestion(jobId, onEvent) {
  return consumeEventStream(`/api/ingestions/${encodeURIComponent(jobId)}/events`, {}, onEvent);
}
