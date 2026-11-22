async function responseError(response) {
  const payload = await response.json().catch(() => ({}));
  return new Error(payload.detail || `API gagal (${response.status}).`);
}

const DEFAULT_STREAM_TIMEOUT_MS = 120000;

function abortReason(signal) {
  const reason = signal?.reason;
  if (reason && typeof reason === "object" && "name" in reason) return reason;
  if (typeof reason === "string" && reason) return new DOMException(reason, "AbortError");
  return new DOMException("Permintaan dibatalkan.", "AbortError");
}

export async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function consumeEventStream(path, options, onEvent, settings = {}) {
  const { signal, timeoutMs = DEFAULT_STREAM_TIMEOUT_MS } = settings;
  const controller = new AbortController();
  const onExternalAbort = () => controller.abort(abortReason(signal));

  if (signal) {
    if (signal.aborted) onExternalAbort();
    else signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  const timer = timeoutMs > 0
    ? setTimeout(() => controller.abort(new DOMException(
        "Waktu tunggu stream habis. Periksa koneksi ke API, lalu coba lagi.",
        "TimeoutError",
      )), timeoutMs)
    : null;

  let reader = null;
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    if (!response.ok) throw await responseError(response);
    if (!response.body) throw new Error("Browser tidak menyediakan stream respons.");

    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    function dispatch(frame) {
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) return;
      let event;
      try {
        event = JSON.parse(data);
      } catch {
        throw new Error("Frame SSE tidak valid. Periksa koneksi ke API, lalu coba lagi.");
      }
      onEvent(event);
    }

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        dispatch(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
  } finally {
    if (timer) clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onExternalAbort);
    if (reader) reader.cancel().catch(() => {});
  }
}
