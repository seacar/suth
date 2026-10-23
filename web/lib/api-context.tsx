"use client";

import { createContext, useContext, useMemo } from "react";

interface ApiConfig {
  baseUrl: string;
  /** SUTH_API_TOKEN; null when the API runs without auth. */
  token: string | null;
}

const ApiConfigContext = createContext<ApiConfig | null>(null);

export function ApiProvider({
  apiBaseUrl,
  apiToken,
  children,
}: {
  apiBaseUrl: string;
  apiToken: string | null;
  children: React.ReactNode;
}) {
  const value = useMemo(() => ({ baseUrl: apiBaseUrl, token: apiToken }), [apiBaseUrl, apiToken]);
  return <ApiConfigContext.Provider value={value}>{children}</ApiConfigContext.Provider>;
}

function useApiConfig(): ApiConfig {
  const value = useContext(ApiConfigContext);
  if (!value) throw new Error("useApi must be used within an ApiProvider");
  return value;
}

/** Talks only to the Local Control API — never Postgres directly, and never
 * re-implements any harness logic (mirrors gui/Sources/SuthGUI/APIClient.swift). */
export function useApi() {
  const { baseUrl, token } = useApiConfig();

  return useMemo(() => {
    async function request<T>(path: string, init?: RequestInit): Promise<T> {
      const headers = new Headers(init?.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const res = await fetch(`${baseUrl}${path}`, { ...init, headers });
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

    // WebSockets and <img>/<video> can't send an Authorization header, so
    // those URLs carry the token as a query parameter instead.
    function authedUrl(path: string): URL {
      const url = new URL(`${baseUrl}${path}`);
      if (token) url.searchParams.set("token", token);
      return url;
    }

    function wsUrl(path: string): string {
      const url = authedUrl(path);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      return url.toString();
    }

    function screenshotUrl(sessionId: string, stepIndex: number): string {
      return authedUrl(`/runs/${sessionId}/screenshots/${stepIndex}`).toString();
    }

    function videoUrl(sessionId: string): string {
      return authedUrl(`/runs/${sessionId}/video`).toString();
    }

    return { baseUrl, request, wsUrl, screenshotUrl, videoUrl };
  }, [baseUrl, token]);
}
