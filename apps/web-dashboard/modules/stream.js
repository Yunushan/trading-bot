export function buildDashboardStreamUrl(baseUrl, path, params = {}) {
  const search = new URLSearchParams(params);
  const query = search.toString();
  return `${String(baseUrl || "").replace(/\/+$/, "")}${path}${query ? `?${query}` : ""}`;
}

export function parseServerSentEvent(block) {
  const event = {
    name: "message",
    data: "",
  };
  const dataLines = [];
  for (const rawLine of String(block || "").split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) {
      continue;
    }
    const separatorIndex = rawLine.indexOf(":");
    const field = separatorIndex === -1 ? rawLine : rawLine.slice(0, separatorIndex);
    let value = separatorIndex === -1 ? "" : rawLine.slice(separatorIndex + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      event.name = value || "message";
    } else if (field === "data") {
      dataLines.push(value);
    }
  }
  event.data = dataLines.join("\n");
  return event;
}

export function supportsDashboardStream() {
  return (
    typeof globalThis.fetch === "function"
    && typeof globalThis.AbortController === "function"
    && typeof globalThis.TextDecoder === "function"
  );
}

async function dispatchEventBlocks(response, onDashboard) {
  const reader = response.body?.getReader?.();
  if (!reader) {
    throw new Error("Response body streaming is not available.");
  }
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      break;
    }
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseServerSentEvent(block);
      if (event.name === "dashboard" && event.data) {
        onDashboard(JSON.parse(event.data));
      }
      boundary = buffer.indexOf("\n\n");
    }
  }

  const trailing = buffer.trim();
  if (trailing) {
    const event = parseServerSentEvent(trailing);
    if (event.name === "dashboard" && event.data) {
      onDashboard(JSON.parse(event.data));
    }
  }
}

export function createDashboardStream({
  streamUrl,
  headers = {},
  fetchImpl = globalThis.fetch,
  onOpen = () => {},
  onDashboard = () => {},
  onError = () => {},
} = {}) {
  const controller = new AbortController();
  let opened = false;

  const closed = (async () => {
    try {
      const response = await fetchImpl(streamUrl, {
        headers: {
          Accept: "text/event-stream",
          ...headers,
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error(`${response.status} ${response.statusText || "Stream request failed"}`);
        error.status = response.status;
        throw error;
      }
      opened = true;
      onOpen();
      await dispatchEventBlocks(response, onDashboard);
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      onError(error, { opened });
    }
  })();

  return {
    close() {
      controller.abort();
    },
    closed,
    get opened() {
      return opened;
    },
  };
}
