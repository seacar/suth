"use client";

import type { CSSProperties } from "react";
import { Loader2, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "@/lib/api-context";
import { useProject } from "@/lib/project-context";
import { Sparkline } from "@/components/Sparkline";
import { SessionReplay } from "@/components/SessionReplay";
import { PageHeader } from "@/components/PageHeader";
import { aggregateFrictionTrend, formatDuration, formatVerdict, formatWhen, frictionColor, verdictTone, videoDurationSeconds } from "@/lib/format";
import type { SessionRow } from "@/lib/types";

type SortKey = "replay" | "started" | "project" | "persona" | "verdict" | "friction" | "caller";
type SortDir = "asc" | "desc";

// Runs are triggered and updated from other processes too (CLI, MCP, another
// dev's session) — nothing pushes those into this page, so it polls instead
// of relying on a manual refresh to see new/finished runs.
const POLL_INTERVAL_MS = 5000;

const COLUMNS: { key: SortKey; label: string; defaultDir: SortDir }[] = [
  { key: "replay", label: "Replay", defaultDir: "desc" },
  { key: "started", label: "Started", defaultDir: "desc" },
  { key: "project", label: "Project", defaultDir: "asc" },
  { key: "persona", label: "Persona", defaultDir: "asc" },
  { key: "verdict", label: "Verdict", defaultDir: "asc" },
  { key: "friction", label: "Friction", defaultDir: "desc" },
  { key: "caller", label: "Caller", defaultDir: "asc" },
];

export default function HistoryPage() {
  const api = useApi();
  const { projectId: projectFilter } = useProject();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [openSessionId, setOpenSessionId] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "started", dir: "desc" });

  useEffect(() => {
    let cancelled = false;
    const query = projectFilter ? `?project_id=${encodeURIComponent(projectFilter)}&limit=30` : "?limit=30";

    function load() {
      api
        .request<SessionRow[]>(`/sessions/recent${query}`)
        .then((rows) => {
          if (!cancelled) setSessions(rows);
        })
        .catch(() => {});
    }

    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [api, projectFilter]);

  const trendData = useMemo(() => aggregateFrictionTrend(sessions), [sessions]);

  const sortedSessions = useMemo(() => {
    const next = [...sessions];
    const direction = sort.dir === "asc" ? 1 : -1;
    next.sort((a, b) => {
      if (sort.key === "replay") return compareReplayLength(a, b, direction);
      return compareSessions(a, b, sort.key as Exclude<SortKey, "replay">) * direction;
    });
    return next;
  }, [sessions, sort]);

  function toggleSort(key: SortKey) {
    setSort((current) => {
      if (current.key === key) {
        return { key, dir: current.dir === "asc" ? "desc" : "asc" };
      }
      const column = COLUMNS.find((item) => item.key === key);
      return { key, dir: column?.defaultDir ?? "asc" };
    });
  }

  return (
    <>
      <PageHeader
        eyebrow="Memory"
        title="History"
        description="Recent sessions across callers. Click a row to open the replay and transcript, or sort any column."
      />

      <section className="panel">
        <div className="panel-head">
          <h2>Friction trend</h2>
          <span className="muted">{sessions.length} recent runs</span>
        </div>
        <div className="panel-body">
          <Sparkline data={trendData} />
        </div>
      </section>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <div className="panel-head">
          <h2>Recent runs</h2>
        </div>
        <div className="panel-body" style={{ paddingTop: "0.5rem" }}>
          {sessions.length === 0 ? (
            <div className="empty">
              <strong>No sessions yet</strong>
              Finished runs from the web app, CLI, or MCP will show up here.
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {COLUMNS.map((column) => (
                      <SortHeader
                        key={column.key}
                        column={column}
                        active={sort.key === column.key}
                        dir={sort.key === column.key ? sort.dir : null}
                        onSort={toggleSort}
                      />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedSessions.map((s) => (
                    <tr key={s.id} className="clickable" onClick={() => setOpenSessionId(s.id)}>
                      <td title={s.video_ref ? "Watch replay" : "No replay video"}>
                        {s.video_ref ? (
                          <span className="replay-cell">
                            <PlayGlyph />
                            <span className="mono">{formatDuration(videoDurationSeconds(s))}</span>
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="mono">{formatWhen(s.started_at)}</td>
                      <td>{s.project_id}</td>
                      <td>{s.persona_id}</td>
                      <td>
                        <span className={`badge ${verdictTone(s.verdict)}`}>
                          {verdictTone(s.verdict) === "running" && (
                            <Loader2 className="spin" size={11} aria-hidden="true" />
                          )}
                          {formatVerdict(s.verdict ?? "running")}
                        </span>
                      </td>
                      <td>
                        <FrictionScore score={s.friction_score} />
                      </td>
                      <td className="mono muted">{s.caller || "cli"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {openSessionId && <SessionReplay sessionId={openSessionId} onClose={() => setOpenSessionId(null)} />}
    </>
  );
}

function SortHeader({
  column,
  active,
  dir,
  onSort,
}: {
  column: (typeof COLUMNS)[number];
  active: boolean;
  dir: SortDir | null;
  onSort: (key: SortKey) => void;
}) {
  return (
    <th className="sortable" aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className={active ? "th-sort active" : "th-sort"}
        onClick={() => onSort(column.key)}
      >
        {column.label}
        <span className={dir ? `sort-glyph ${dir}` : "sort-glyph"} aria-hidden="true">
          <i className="up" />
          <i className="down" />
        </span>
      </button>
    </th>
  );
}

function PlayGlyph() {
  return (
    <span className="replay-play" aria-label="Watch replay">
      <Play size={14} fill="currentColor" strokeWidth={0} aria-hidden="true" />
    </span>
  );
}

function FrictionScore({ score }: { score: number | null }) {
  if (score === null) return <span className="muted">—</span>;
  const color = frictionColor(score);
  return (
    <span className="friction-score mono" style={{ "--friction-color": color } as CSSProperties}>
      {score.toFixed(1)}
    </span>
  );
}

function compareReplayLength(a: SessionRow, b: SessionRow, direction: number): number {
  const left = videoDurationSeconds(a);
  const right = videoDurationSeconds(b);
  if (left == null && right == null) return 0;
  if (left == null) return 1;
  if (right == null) return -1;
  return (left - right) * direction;
}

function compareSessions(a: SessionRow, b: SessionRow, key: Exclude<SortKey, "replay">): number {
  switch (key) {
    case "started":
      return toTime(a.started_at) - toTime(b.started_at);
    case "project":
      return compareText(a.project_id, b.project_id);
    case "persona":
      return compareText(a.persona_id, b.persona_id);
    case "verdict":
      return compareText(a.verdict, b.verdict);
    case "friction":
      return (a.friction_score ?? Number.NEGATIVE_INFINITY) - (b.friction_score ?? Number.NEGATIVE_INFINITY);
    case "caller":
      return compareText(a.caller, b.caller);
  }
}

function compareText(a: string | null | undefined, b: string | null | undefined): number {
  return (a ?? "").localeCompare(b ?? "", undefined, { numeric: true, sensitivity: "base" });
}

function toTime(iso: string): number {
  const value = new Date(iso).getTime();
  return Number.isNaN(value) ? 0 : value;
}
