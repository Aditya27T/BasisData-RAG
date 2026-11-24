import { consumeEventStream, requestJson } from "./http.js";

function workspaceParam(workspace) {
  return encodeURIComponent((workspace || "docs").trim() || "docs");
}

export function listDocuments(workspace, settings = {}) {
  return requestJson(`/api/documents?workspace=${workspaceParam(workspace)}`, settings);
}

export function startIngestion(file, workspace, force = false, settings = {}) {
  const form = new FormData();
  form.set("file", file);
  return requestJson(
    `/api/ingestions?workspace=${workspaceParam(workspace)}&force=${force}`,
    { method: "POST", body: form, ...settings },
  );
}

export function streamIngestion(jobId, onEvent, settings = {}) {
  return consumeEventStream(`/api/ingestions/${encodeURIComponent(jobId)}/events`, {}, onEvent, settings);
}
