import { writable } from "svelte/store";
import { listDocuments, startIngestion, streamIngestion } from "../api/documents.js";

export function createDocumentsController() {
  const state = writable({
    documents: [],
    loading: false,
    error: "",
    uploadBusy: false,
    ingestionJob: null,
    ingestionLogs: [],
  });

  async function load(workspace) {
    state.update((current) => ({ ...current, loading: true, error: "" }));
    try {
      const result = await listDocuments(workspace);
      state.update((current) => ({ ...current, documents: result.documents || [] }));
    } catch (error) {
      state.update((current) => ({ ...current, error: error.message }));
    } finally {
      state.update((current) => ({ ...current, loading: false }));
    }
  }

  async function upload(file, workspace, force) {
    state.update((current) => ({
      ...current,
      uploadBusy: true,
      error: "",
      ingestionJob: null,
      ingestionLogs: [],
    }));
    try {
      const accepted = await startIngestion(file, workspace, force);
      state.update((current) => ({ ...current, ingestionJob: accepted }));
      await streamIngestion(accepted.job_id, (event) => {
        state.update((current) => {
          const log = {
            sequence: event.sequence ?? current.ingestionLogs.length + 1,
            kind: event.event || "progress",
            message: event.message || event.stage || "Ada aktivitas ingest.",
          };
          const job = event.status
            ? { ...current.ingestionJob, status: event.status, result: event.result, error: event.status === "failed" ? event.message : null }
            : current.ingestionJob;
          return { ...current, ingestionJob: job, ingestionLogs: [...current.ingestionLogs, log] };
        });
      });
      await load(workspace);
    } catch (error) {
      state.update((current) => ({
        ...current,
        error: error.message,
        ingestionJob: current.ingestionJob
          ? { ...current.ingestionJob, status: "failed", error: error.message }
          : null,
      }));
    } finally {
      state.update((current) => ({ ...current, uploadBusy: false }));
    }
  }

  return { subscribe: state.subscribe, load, upload };
}
