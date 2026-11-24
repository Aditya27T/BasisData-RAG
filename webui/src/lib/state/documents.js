import { get, writable } from "svelte/store";
import { listDocuments, startIngestion, streamIngestion } from "../api/documents.js";

function isAbort(error) {
  return error?.name === "AbortError";
}

export function createDocumentsController() {
  const state = writable({
    documents: [],
    loading: false,
    error: "",
    uploadBusy: false,
    ingestionJob: null,
    ingestionLogs: [],
  });
  let loadGeneration = 0;
  let uploadGeneration = 0;
  let activeLoad = null;
  let activeUpload = null;

  function abortLoad() {
    if (!activeLoad) return;
    loadGeneration += 1;
    activeLoad.abort(new DOMException("Permintaan dibatalkan.", "AbortError"));
    activeLoad = null;
  }

  function abortUpload() {
    if (!activeUpload) return;
    uploadGeneration += 1;
    activeUpload.abort(new DOMException("Permintaan dibatalkan.", "AbortError"));
    activeUpload = null;
  }

  function releaseLoad(controller) {
    if (activeLoad === controller) activeLoad = null;
  }

  function releaseUpload(controller) {
    if (activeUpload === controller) activeUpload = null;
  }

  async function load(workspace) {
    abortLoad();
    const mine = ++loadGeneration;
    const controller = new AbortController();
    activeLoad = controller;
    state.update((current) => ({ ...current, loading: true, error: "" }));
    try {
      const result = await listDocuments(workspace, { signal: controller.signal });
      if (mine !== loadGeneration) return;
      state.update((current) => ({ ...current, documents: result.documents || [] }));
    } catch (error) {
      if (mine !== loadGeneration || isAbort(error)) return;
      state.update((current) => ({
        ...current,
        error: error.message || "Daftar dokumen gagal dimuat. Periksa API, lalu coba lagi.",
      }));
    } finally {
      releaseLoad(controller);
      if (mine === loadGeneration) {
        state.update((current) => ({ ...current, loading: false }));
      }
    }
  }

  async function upload(file, workspace, force) {
    abortUpload();
    const mine = ++uploadGeneration;
    const controller = new AbortController();
    activeUpload = controller;
    state.update((current) => ({
      ...current,
      uploadBusy: true,
      error: "",
      ingestionJob: null,
      ingestionLogs: [],
    }));
    try {
      const accepted = await startIngestion(file, workspace, force, { signal: controller.signal });
      if (mine !== uploadGeneration) return;
      state.update((current) => ({ ...current, ingestionJob: accepted }));
      await streamIngestion(accepted.job_id, (event) => {
        if (mine !== uploadGeneration) return;
        state.update((current) => {
          const log = {
            sequence: event.sequence ?? Date.now(),
            kind: event.event || "progress",
            message: event.message || event.stage || "Ada aktivitas ingest.",
          };
          const job = event.status
            ? { ...current.ingestionJob, status: event.status, result: event.result, error: event.status === "failed" ? event.message : null }
            : current.ingestionJob;
          return { ...current, ingestionJob: job, ingestionLogs: [...current.ingestionLogs, log].slice(-8) };
        });
      }, { signal: controller.signal });
      if (mine !== uploadGeneration) return;
      await load(workspace);
    } catch (error) {
      if (mine !== uploadGeneration || isAbort(error)) return;
      state.update((current) => ({
        ...current,
        error: error.message || "Unggah gagal. Periksa koneksi ke API, lalu coba lagi.",
        ingestionJob: current.ingestionJob
          ? { ...current.ingestionJob, status: "failed", error: error.message }
          : null,
      }));
    } finally {
      releaseUpload(controller);
      if (mine === uploadGeneration) {
        state.update((current) => ({ ...current, uploadBusy: false }));
      }
    }
  }

  function cancelUpload() {
    if (!activeUpload && !get(state).uploadBusy) return;
    abortUpload();
    state.update((current) => ({
      ...current,
      uploadBusy: false,
      ingestionJob: current.ingestionJob
        ? { ...current.ingestionJob, status: "cancelled" }
        : null,
      ingestionLogs: [
        ...current.ingestionLogs,
        { sequence: Date.now(), kind: "batal", message: "Unggah dibatalkan." },
      ].slice(-8),
    }));
  }

  function reset() {
    abortLoad();
    abortUpload();
    state.set({
      documents: [],
      loading: false,
      error: "",
      uploadBusy: false,
      ingestionJob: null,
      ingestionLogs: [],
    });
  }

  return { subscribe: state.subscribe, load, upload, cancelUpload, reset };
}
