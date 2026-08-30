import type { SessionRow } from "@/lib/types";

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.replace("T", " ").slice(0, 19);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Formats a date for chart X-axis ticks (e.g. "Aug 29, 8:02 PM"). */
export function formatAxisDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.replace("T", " ").slice(0, 16);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function sessionOptionLabel(session: SessionRow): string {
  const verdict = formatVerdict(session.verdict ?? "running");
  const score = session.friction_score !== null ? session.friction_score.toFixed(1) : "—";
  return `${formatWhen(session.started_at)} · ${session.persona_id} · ${verdict} · ${score}`;
}

/** e.g. dead_click → Dead Click, objective_met → Objective Met */
export function formatVerdict(verdict: string | null | undefined): string {
  if (!verdict) return "Running";
  return verdict
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

/** Prefer the stored container duration; fall back to recording wall-clock. */
export function videoDurationSeconds(session: SessionRow): number | null {
  if (typeof session.video_duration_seconds === "number") {
    return session.video_duration_seconds;
  }
  if (!session.video_ref || !session.ended_at || !session.video_started_at) return null;
  const ms = Date.parse(session.ended_at) - Date.parse(session.video_started_at);
  if (!Number.isFinite(ms) || ms < 0) return null;
  return ms / 1000;
}

export function verdictTone(verdict: string | null | undefined): "ok" | "bad" | "running" | "idle" {
  if (!verdict) return "running";
  if (verdict === "objective_met") return "ok";
  if (verdict === "running") return "running";
  return "bad";
}

/** 0 = smooth run, 1 = worst-case friction (scores above max clamp to 1). */
export function frictionIntensity(score: number, max = 15): number {
  return Math.min(Math.max(score / max, 0), 1);
}

/** Continuous green → orange → red scale for friction scores. */
export function frictionColor(score: number, max = 15): string {
  const t = frictionIntensity(score, max);
  if (t <= 0.5) {
    const u = t * 2;
    return `color-mix(in srgb, var(--green) ${(1 - u) * 100}%, var(--orange) ${u * 100}%)`;
  }
  const u = (t - 0.5) * 2;
  return `color-mix(in srgb, var(--orange) ${(1 - u) * 100}%, var(--red) ${u * 100}%)`;
}

export interface TrendRunDetail {
  id: string;
  persona_id: string;
  score: number;
  verdict: string | null;
}

export interface TrendPoint {
  id?: string;
  score: number;
  started_at?: string;
  persona_id?: string;
  verdict?: string | null;
  runs?: TrendRunDetail[];
}

/**
 * Groups session runs triggered within the same minute and averages their
 * friction scores into a single chronological data point for the trend chart.
 */
export function aggregateFrictionTrend(sessions: SessionRow[]): TrendPoint[] {
  const scored = sessions.filter((s) => s.friction_score !== null);
  if (scored.length === 0) return [];

  // Sort chronological (oldest to newest)
  const sorted = [...scored].sort((a, b) => {
    const timeA = new Date(a.started_at).getTime() || 0;
    const timeB = new Date(b.started_at).getTime() || 0;
    return timeA - timeB;
  });

  // Group runs triggered within the same minute (based on started_at)
  const groups: Map<number, SessionRow[]> = new Map();
  for (const s of sorted) {
    const time = new Date(s.started_at).getTime();
    const minuteBucket = Number.isNaN(time) ? 0 : Math.floor(time / 60000);
    const existing = groups.get(minuteBucket);
    if (existing) {
      existing.push(s);
    } else {
      groups.set(minuteBucket, [s]);
    }
  }

  const points: TrendPoint[] = [];
  for (const group of groups.values()) {
    const totalScore = group.reduce((sum, s) => sum + (s.friction_score as number), 0);
    const avgScore = totalScore / group.length;
    const runs: TrendRunDetail[] = group.map((s) => ({
      id: s.id,
      persona_id: s.persona_id,
      score: s.friction_score as number,
      verdict: s.verdict,
    }));

    points.push({
      id: group.length === 1 ? group[0].id : undefined,
      score: avgScore,
      started_at: group[0].started_at,
      persona_id: group.length === 1 ? group[0].persona_id : `${group.length} personas`,
      verdict: group.length === 1 ? group[0].verdict : null,
      runs,
    });
  }

  return points;
}
