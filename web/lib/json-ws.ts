/** Subscribes to a JSON-message WebSocket. Returns an unsubscribe function.
 * Mirrors the imperative receive-loop in APIClient.swift's wsJSONStream,
 * since callers here (batch runs) need several concurrent subscriptions
 * driven from event handlers rather than one declarative mount effect. */
export function subscribeJsonWs<T>(
  url: string,
  onMessage: (value: T) => void,
  onClose?: () => void
): () => void {
  const socket = new WebSocket(url);

  socket.onmessage = (event) => {
    if (typeof event.data !== "string") return;
    try {
      onMessage(JSON.parse(event.data) as T);
    } catch {
      // ignore malformed frames
    }
  };
  socket.onclose = () => onClose?.();
  socket.onerror = () => socket.close();

  return () => socket.close();
}
