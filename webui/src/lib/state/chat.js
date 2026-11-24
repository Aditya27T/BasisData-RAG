import { get, writable } from "svelte/store";
import { streamChat } from "../api/chat.js";
import { graphFromAnswer } from "./chat-graph.js";

function isAbort(error) {
  return error?.name === "AbortError";
}

export function createChatController() {
  const state = writable({ messages: [], busy: false, error: "", stage: "", progressLog: [] });
  let nextId = 1;
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

  async function send(question, workspace) {
    const text = question.trim();
    if (!text) return;
    abortActive();
    const mine = ++generation;
    const controller = new AbortController();
    active = controller;

    state.update((current) => ({
      ...current,
      messages: [...current.messages, { id: nextId++, role: "user", text }],
      busy: true,
      error: "",
      stage: "Menghubungkan ke pipeline…",
      progressLog: [{ id: nextId++, kind: "request", message: "Permintaan diterima." }],
    }));

    let answer = null;
    let streamError = "";
    try {
      await streamChat(text, workspace, (event) => {
        if (mine !== generation) return;
        if (event.event === "progress") {
          const entry = {
            id: nextId++,
            kind: event.kind || event.stage || "status",
            message: event.message || "Pipeline memproses pertanyaan.",
          };
          state.update((current) => ({
            ...current,
            stage: entry.message,
            progressLog: [...current.progressLog, entry].slice(-12),
          }));
        } else if (event.event === "complete") {
          answer = event.data;
        } else if (event.event === "error") {
          streamError = event.message || "Proses tanya-jawab gagal.";
        }
      }, { signal: controller.signal });
      if (mine !== generation) return;
      if (streamError) throw new Error(streamError);
      if (!answer) throw new Error("Stream selesai tanpa hasil jawaban. Coba kirim pertanyaan lagi.");
      state.update((current) => ({
        ...current,
        messages: [...current.messages, {
          id: nextId++,
          role: "assistant",
          text: answer.answer,
          refused: answer.refused,
          sources: answer.sources || [],
          graph: graphFromAnswer(answer.entities || [], answer.relationships || []),
        }],
      }));
    } catch (error) {
      if (mine !== generation || isAbort(error)) return;
      state.update((current) => ({
        ...current,
        error: error.message || "Permintaan gagal. Periksa koneksi ke API, lalu coba lagi.",
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
        { id: nextId++, kind: "batal", message: "Permintaan dibatalkan." },
      ].slice(-12),
    }));
  }

  function reset() {
    abortActive();
    state.set({ messages: [], busy: false, error: "", stage: "", progressLog: [] });
  }

  return { subscribe: state.subscribe, send, cancel, reset };
}
