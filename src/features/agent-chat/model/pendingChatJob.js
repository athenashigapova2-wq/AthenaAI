const KEY_PREFIX = "athena:pending-chat-job:";

function storage() {
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

export function createChatRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `chat:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

export function loadPendingChatJob(userId) {
  if (!userId) return null;
  try {
    return JSON.parse(storage()?.getItem(`${KEY_PREFIX}${userId}`) || "null");
  } catch {
    return null;
  }
}

export function savePendingChatJob(userId, value) {
  if (!userId) return;
  storage()?.setItem(`${KEY_PREFIX}${userId}`, JSON.stringify(value));
}

export function clearPendingChatJob(userId, requestId) {
  if (!userId) return;
  const current = loadPendingChatJob(userId);
  if (!requestId || current?.requestId === requestId) {
    storage()?.removeItem(`${KEY_PREFIX}${userId}`);
  }
}
