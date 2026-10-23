import { subscribeJsonWs } from "@/lib/json-ws";
import type { StepEvent } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;
const ACTIVE_STATUSES = new Set(["queued", "running"]);

interface WatchApi {
  request<T>(path: string, init?: RequestInit): Promise<T>;
  wsUrl(path: string): string;
}

/** Streams a session's step events and calls `onDone` exactly once when it
 * ends. If the WebSocket drops before the "done" frame (API restart, network
 * blip), falls back to polling /runs/{id}/status so the UI can't get stuck
 * showing "Running" forever. Returns a cancel function. */
export function watchSession(
  api: WatchApi,
  sessionId: string,
  onStep: (event: StepEvent) => void,
  onDone: () => void
): () => void {
  let finished = false;
  let cancelled = false;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;

  const finish = () => {
    if (finished || cancelled) return;
    finished = true;
    onDone();
  };

  const poll = () => {
    if (finished || cancelled) return;
    api
      .request<{ status: string }>(`/runs/${sessionId}/status`)
      .then(({ status }) => {
        if (ACTIVE_STATUSES.has(status)) pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
        else finish();
      })
      // Unknown session or API down: stop waiting and let onDone's report
      // fetch surface the error instead of spinning silently.
      .catch(finish);
  };

  const unsubscribe = subscribeJsonWs<StepEvent>(
    api.wsUrl(`/runs/${sessionId}/stream`),
    (event) => {
      if (event.type === "step") onStep(event);
      else if (event.type === "done") finish();
    },
    poll
  );

  return () => {
    cancelled = true;
    clearTimeout(pollTimer);
    unsubscribe();
  };
}
