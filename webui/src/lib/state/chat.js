import { writable } from "svelte/store";
import { streamChat } from "../api/chat.js";
import { graphFromAnswer } from "./chat-graph.js";

export function createChatController() {
  const state = writable({ messages: [], busy: false, error: "", stage: "", progressLog: [] });
  let nextId = 1;

  async function send(question, workspace) {
    const text = question.trim();
    if (!text) return;
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
      });
      if (streamError) throw new Error(streamError);
      if (!answer) throw new Error("Stream selesai tanpa hasil jawaban.");
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
      state.update((current) => ({ ...current, error: error.message }));
    } finally {
      state.update((current) => ({ ...current, busy: false, stage: "" }));
    }
  }

  return { subscribe: state.subscribe, send };
}
