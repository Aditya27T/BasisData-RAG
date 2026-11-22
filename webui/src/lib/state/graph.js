import { get, writable } from "svelte/store";
import { streamGraph } from "../api/graph.js";
import { layoutGraph } from "./graph-layout.js";

function isAbort(error) {
  return error?.name === "AbortError";
}

export function createGraphController() {
  const state = writable({
    nodes: [],
    edges: [],
    positions: {},
    selectedNodeId: "",
    busy: false,
    error: "",
    stage: "",
    truncated: false,
    progressLog: [],
  });
  let generation = 0;
  let active = null;

  function abortActive() {
    if (!active) return;
    generation += 1;
    active.abort(new DOMException("Permintaan dibatalkan.", "AbortError"));
    active = null;
  }

  function release(controller) {
    if (active === controller) active = null;
  }

  async function load(workspace) {
    abortActive();
    const mine = ++generation;
    const controller = new AbortController();
    active = controller;

    state.update((current) => ({
      ...current,
      busy: true,
      error: "",
      stage: "Memulai pembacaan graph…",
      progressLog: [{ id: Date.now(), kind: "request", message: "Permintaan graph diterima." }],
    }));
    let result = null;
    let streamError = "";
    try {
      await streamGraph(workspace, 80, (event) => {
        if (mine !== generation) return;
        if (event.event === "progress") {
          const entry = {
            id: Date.now() + Math.random(),
            kind: event.stage || "progress",
            message: event.message || "Membaca graph.",
          };
          state.update((current) => ({
            ...current,
            stage: entry.message,
            progressLog: [...current.progressLog, entry].slice(-12),
          }));
        } else if (event.event === "complete") {
          result = event.data;
        } else if (event.event === "error") {
          streamError = event.message || "Graph gagal dimuat.";
        }
      }, { signal: controller.signal });
      if (mine !== generation) return;
      if (streamError) throw new Error(streamError);
      if (!result) throw new Error("Stream selesai tanpa data graph. Coba muat ulang graph.");
      const layout = layoutGraph(result);
      state.update((current) => ({
        ...current,
        nodes: result.nodes || [],
        edges: layout.edges,
        positions: layout.positions,
        selectedNodeId: result.nodes?.[0]?.id || "",
        truncated: Boolean(result.truncated),
      }));
    } catch (error) {
      if (mine !== generation || isAbort(error)) return;
      state.update((current) => ({
        ...current,
        error: error.message || "Graph gagal dimuat. Periksa koneksi ke API, lalu coba lagi.",
        nodes: [],
        edges: [],
        positions: {},
        selectedNodeId: "",
      }));
    } finally {
      release(controller);
      if (mine === generation) {
        state.update((current) => ({ ...current, busy: false, stage: "" }));
      }
    }
  }

  function cancel() {
    if (!active && !get(state).busy) return;
    abortActive();
    state.update((current) => ({
      ...current,
      busy: false,
      stage: "",
      progressLog: [
        ...current.progressLog,
        { id: Date.now(), kind: "batal", message: "Pembacaan graph dibatalkan." },
      ].slice(-12),
    }));
  }

  function reset() {
    abortActive();
    state.set({
      nodes: [],
      edges: [],
      positions: {},
      selectedNodeId: "",
      busy: false,
      error: "",
      stage: "",
      truncated: false,
      progressLog: [],
    });
  }

  function selectNode(nodeId) {
    state.update((current) => ({ ...current, selectedNodeId: nodeId }));
  }

  return { subscribe: state.subscribe, load, cancel, reset, selectNode };
}
