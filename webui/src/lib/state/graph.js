import { writable } from "svelte/store";
import { streamGraph } from "../api/graph.js";
import { layoutGraph } from "./graph-layout.js";

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

  async function load(workspace) {
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
      });
      if (streamError) throw new Error(streamError);
      if (!result) throw new Error("Stream selesai tanpa data graph.");
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
      state.update((current) => ({ ...current, error: error.message, nodes: [], edges: [], positions: {}, selectedNodeId: "" }));
    } finally {
      state.update((current) => ({ ...current, busy: false, stage: "" }));
    }
  }

  function selectNode(nodeId) {
    state.update((current) => ({ ...current, selectedNodeId: nodeId }));
  }

  return { subscribe: state.subscribe, load, selectNode };
}
