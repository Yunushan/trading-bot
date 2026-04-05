import { authHeaders, state } from "./state.js";

export async function requestJson(
  path,
  { method = "GET", payload = null, allowUnauthorized = false } = {},
) {
  const headers = {
    Accept: "application/json",
    ...authHeaders(),
  };
  const options = {
    method,
    headers,
  };
  if (payload !== null) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(`${state.baseUrl}${path}`, options);
  if (response.status === 401 && allowUnauthorized) {
    return { unauthorized: true };
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ""}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export function fetchJson(path, options = {}) {
  return requestJson(path, { ...options, method: "GET" });
}

export function sendJson(method, path, payload) {
  return requestJson(path, { method, payload });
}
