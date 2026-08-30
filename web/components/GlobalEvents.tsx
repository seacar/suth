"use client";

import { useEffect } from "react";
import { useApi } from "@/lib/api-context";
import type { GlobalEvent } from "@/lib/types";
import { formatVerdict } from "@/lib/format";

const RECONNECT_DELAY_MS = 3000;

/** Every session's completion, from any process (CLI, MCP, another dev's CLI
 * run) — not just runs started from this app. Mirrors NotificationManager.swift
 * + AppState.swift's startGlobalWatch, fed by the API's global /events socket. */
export function GlobalEvents() {
  const { wsUrl } = useApi();

  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (cancelled) return;
      socket = new WebSocket(wsUrl("/events"));

      socket.onmessage = (event) => {
        if (typeof event.data !== "string") return;
        try {
          const value = JSON.parse(event.data) as GlobalEvent;
          notify(value);
        } catch {
          // ignore malformed frames
        }
      };

      const reconnect = () => {
        if (cancelled) return;
        timer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
      socket.onclose = reconnect;
      socket.onerror = () => socket?.close();
    }

    connect();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [wsUrl]);

  return null;
}

function notify(event: GlobalEvent) {
  if (event.type !== "session_finished") return;
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;

  const score = event.friction_score !== null ? event.friction_score.toFixed(1) : "?";
  const caller = event.caller ? ` (${event.caller})` : "";
  new Notification(`suth: ${event.project_id}`, {
    body: `${formatVerdict(event.verdict ?? "finished")} — friction ${score}${caller}`,
  });
}
