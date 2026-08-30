"use client";

import { createContext, useContext, useMemo } from "react";

const ApiBaseUrlContext = createContext<string | null>(null);

export function ApiProvider({
  apiBaseUrl,
  children,
}: {
  apiBaseUrl: string;
  children: React.ReactNode;
}) {
  return <ApiBaseUrlContext.Provider value={apiBaseUrl}>{children}</ApiBaseUrlContext.Provider>;
}

export function useApiBaseUrl(): string {
  const value = useContext(ApiBaseUrlContext);
  if (!value) throw new Error("useApiBaseUrl must be used within an ApiProvider");
  return value;
}

/** Talks only to the Local Control API — never Postgres directly, and never
 * re-implements any harness logic (mirrors gui/Sources/SuthGUI/APIClient.swift). */
export function useApi() {
  const baseUrl = useApiBaseUrl();

  return useMemo(() => {
    async function request<T>(path: string, init?: RequestInit): Promise<T> {
      const res = await fetch(`${baseUrl}${path}`, init);
      if (!res.ok) {
        const message = await res.text().catch(() => `HTTP ${res.status}`);
        let detail = message || `HTTP ${res.status}`;
        try {
          const parsed = JSON.parse(message) as { detail?: unknown };
          if (typeof parsed.detail === "string") detail = parsed.detail;
        } catch {
          /* keep raw body */
        }
        throw new Error(detail);
      }
      return res.json() as Promise<T>;
    }

    function wsUrl(path: string): string {
      const url = new URL(`${baseUrl}${path}`);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      return url.toString();
    }

    function screenshotUrl(sessionId: string, stepIndex: number): string {
      return `${baseUrl}/runs/${sessionId}/screenshots/${stepIndex}`;
    }

    function videoUrl(sessionId: string): string {
      return `${baseUrl}/runs/${sessionId}/video`;
    }

    return { baseUrl, request, wsUrl, screenshotUrl, videoUrl };
  }, [baseUrl]);
}
