async function responseError(response) {
  const payload = await response.json().catch(() => ({}));
  return new Error(payload.detail || `API gagal (${response.status}).`);
}

export async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function consumeEventStream(path, options, onEvent) {
  const response = await fetch(path, options);
  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("Browser tidak menyediakan stream respons.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function dispatch(frame) {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (data) onEvent(JSON.parse(data));
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
}
