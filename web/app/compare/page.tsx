"use client";

import { useEffect, useMemo, useState } from "react";
import { useApi } from "@/lib/api-context";
import { useProject } from "@/lib/project-context";
import { PageHeader } from "@/components/PageHeader";
import { formatVerdict, formatWhen } from "@/lib/format";
import type { ComparisonResult, SessionRow } from "@/lib/types";

function runOptionLabel(session: SessionRow): string {
  const verdict = formatVerdict(session.verdict ?? "running");
  const score = session.friction_score !== null ? session.friction_score.toFixed(1) : "—";
  return `${formatWhen(session.started_at)} · ${verdict} · ${score}`;
}

// Mirrors the History page's polling — a run started elsewhere (CLI, MCP,
// another dev) only becomes comparable once it finishes, and nothing pushes
// that update into this page.
const POLL_INTERVAL_MS = 5000;

export default function ComparePage() {
  const api = useApi();
  const { projectId: projectFilter } = useProject();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const query = projectFilter
      ? `?project_id=${encodeURIComponent(projectFilter)}&limit=200`
      : "?limit=200";

    function load() {
      api
        .request<SessionRow[]>(`/sessions/recent${query}`)
        .then((rows) => {
          if (cancelled) return;
          setSessions(rows);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : String(err));
        });
    }

    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [api, projectFilter]);

  const personaGroups = useMemo(() => {
    const byPersona = new Map<string, SessionRow[]>();
    for (const s of sessions) {
      if (s.verdict === null) continue; // only finished runs are comparable
      const list = byPersona.get(s.persona_id) ?? [];
      list.push(s);
      byPersona.set(s.persona_id, list);
    }
    for (const list of byPersona.values()) {
      list.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
    }
    return Array.from(byPersona.entries()).sort(
      ([, a], [, b]) => new Date(b[0].started_at).getTime() - new Date(a[0].started_at).getTime()
    );
  }, [sessions]);

  return (
    <>
      <PageHeader
        eyebrow="Regression"
        title="Compare"
        description="Diff friction scores and failure taxonomy between runs, one card per persona. Each card defaults to the last two runs — pick a different pair if a persona has more history."
      />

      {error && <p className="error-text">{error}</p>}

      {personaGroups.length === 0 ? (
        <div className="empty">
          <strong>No finished runs yet</strong>
          Run a persona to completion and it will show up here for comparison.
        </div>
      ) : (
        <div className="stack">
          {personaGroups.map(([personaId, runs]) => (
            <PersonaCompareCard key={personaId} personaId={personaId} runs={runs} />
          ))}
        </div>
      )}
    </>
  );
}

function PersonaCompareCard({ personaId, runs }: { personaId: string; runs: SessionRow[] }) {
  const api = useApi();
  const runIds = runs.map((r) => r.id).join(",");

  // Reset the selected pair to "last two runs" whenever this persona's run
  // list changes, without an effect (see https://react.dev/learn/you-might-not-need-an-effect).
  const [pair, setPair] = useState(() => ({
    runIds,
    baselineId: runs[1]?.id ?? "",
    candidateId: runs[0]?.id ?? "",
  }));
  if (pair.runIds !== runIds) {
    setPair({ runIds, baselineId: runs[1]?.id ?? "", candidateId: runs[0]?.id ?? "" });
  }
  const { baselineId, candidateId } = pair;
  const setBaselineId = (id: string) => setPair((p) => ({ ...p, baselineId: id }));
  const setCandidateId = (id: string) => setPair((p) => ({ ...p, candidateId: id }));

  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!baselineId || !candidateId) return;
    let cancelled = false;
    api
      .request<ComparisonResult>(
        `/compare?session_id_a=${encodeURIComponent(baselineId)}&session_id_b=${encodeURIComponent(candidateId)}&regression_threshold=0`
      )
      .then((data) => {
        if (cancelled) return;
        setResult(data);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [api, baselineId, candidateId]);

  const canPickPair = runs.length > 2;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{personaId}</h2>
        <div className="row" style={{ gap: "0.5rem" }}>
          <span className="muted">
            {runs.length} run{runs.length === 1 ? "" : "s"}
          </span>
          {result && (
            <span className={`badge ${result.regressed ? "bad" : "ok"}`}>
              {result.regressed ? "regression" : "no regression"}
            </span>
          )}
        </div>
      </div>
      <div className="panel-body stack">
        {runs.length < 2 ? (
          <div className="empty">
            <strong>Need a second run</strong>
            Run {personaId} again to compare against {formatWhen(runs[0].started_at)}.
          </div>
        ) : (
          <>
            {canPickPair && (
              <div className="split split-wide">
                <div className="field">
                  <label htmlFor={`baseline-${personaId}`}>Baseline</label>
                  <select
                    id={`baseline-${personaId}`}
                    value={baselineId}
                    onChange={(e) => setBaselineId(e.target.value)}
                  >
                    {runs.map((r) => (
                      <option key={r.id} value={r.id} disabled={r.id === candidateId}>
                        {runOptionLabel(r)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor={`candidate-${personaId}`}>Candidate</label>
                  <select
                    id={`candidate-${personaId}`}
                    value={candidateId}
                    onChange={(e) => setCandidateId(e.target.value)}
                  >
                    {runs.map((r) => (
                      <option key={r.id} value={r.id} disabled={r.id === baselineId}>
                        {runOptionLabel(r)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {error && <p className="error-text">{error}</p>}

            {result && (
              <>
                <div className="score-grid">
                  <div className="stat">
                    <div className="stat-label">Baseline</div>
                    <div className="stat-value">{result.baseline_friction_score.toFixed(1)}</div>
                  </div>
                  <div className="stat">
                    <div className="stat-label">Candidate</div>
                    <div className="stat-value">{result.candidate_friction_score.toFixed(1)}</div>
                  </div>
                  <div className="stat">
                    <div className="stat-label">Delta</div>
                    <div className="stat-value" style={{ color: result.regressed ? "var(--red)" : "var(--green)" }}>
                      {result.friction_delta >= 0 ? "+" : ""}
                      {result.friction_delta.toFixed(1)}
                    </div>
                  </div>
                </div>

                <div className="split split-wide">
                  <TaxonomyBar title="Baseline taxonomy" counts={result.baseline_taxonomy_counts} />
                  <TaxonomyBar title="Candidate taxonomy" counts={result.candidate_taxonomy_counts} />
                </div>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function TaxonomyBar({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className="stat">
      <div className="stat-label">{title}</div>
      <div className="taxonomy-list">
        {entries.length === 0 ? (
          <div className="muted">No failure hits</div>
        ) : (
          entries.map(([label, count]) => (
            <div key={label} className="row" style={{ justifyContent: "space-between" }}>
              <span>{formatVerdict(label)}</span>
              <span className="mono">{count}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
