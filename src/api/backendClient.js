const NGROK_FREE_SUFFIX = ".ngrok-free.dev";

/**
 * @param {string | URL} url
 * @param {HeadersInit} headers
 * @returns {Record<string, string>}
 */
export function backendHeaders(url, headers = {}) {
  /** @type {Record<string, string>} */
  const result = {};
  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      result[key] = value;
    });
  } else if (Array.isArray(headers)) {
    for (const [key, value] of headers) result[key] = value;
  } else {
    Object.assign(result, headers);
  }

  try {
    const hostname = new URL(url, globalThis.location?.origin).hostname;
    if (hostname.endsWith(NGROK_FREE_SUFFIX)) {
      // Free ngrok endpoints otherwise return an HTML browser-warning page to
      // Capacitor's WebView, which breaks authenticated API and SSE requests.
      result["ngrok-skip-browser-warning"] = "athena-android";
    }
  } catch {
    // Let fetch report malformed URLs through its normal error contract.
  }
  return result;
}

export function fetchBackend(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: backendHeaders(url, options.headers),
  });
}

export function apiErrorMessage(payload, fallback) {
  const detail = payload?.detail ?? payload?.error;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === "string" ? item : item?.msg))
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") return detail.message;
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return fallback;
}
