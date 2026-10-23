"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api-context";
import { useProject } from "@/lib/project-context";
import { fetchProject } from "@/lib/projects-api";
import { watchSession } from "@/lib/run-watch";
import { formatVerdict } from "@/lib/format";
import { StepRow } from "@/components/StepRow";
import { SessionReplay } from "@/components/SessionReplay";
import { PageHeader } from "@/components/PageHeader";
import type { BatchMember, BatchStarted, PersonaRecord, RunPhase, RunReport, RunStarted, StepEvent } from "@/lib/types";

const VERDICT_OK = "objective_met";

export default function RunPage() {
  const api = useApi();
  const { projectId } = useProject();

  const [personas, setPersonas] = useState<PersonaRecord[]>([]);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<Set<string>>(new Set());
  const [objective, setObjective] = useState("");
  const [environment, setEnvironment] = useState("dev");
  const [projectEnvs, setProjectEnvs] = useState<{ projectId: string; names: string[] } | null>(null);
  const [headed, setHeaded] = useState(true);
  const [stepThrough, setStepThrough] = useState(false);

  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState<RunPhase>({ kind: "idle" });
  const [liveSteps, setLiveSteps] = useState<StepEvent[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [stepThroughWaiting, setStepThroughWaiting] = useState(false);

  const [isBatchMode, setIsBatchMode] = useState(false);
  const [batchStarting, setBatchStarting] = useState(false);
  const [batchMembers, setBatchMembers] = useState<BatchMember[]>([]);
  // Store the id, not a copy: the modal must keep showing live steps.
  const [detailMemberId, setDetailMemberId] = useState<string | null>(null);
  const detailMember = batchMembers.find((m) => m.sessionId === detailMemberId) ?? null;
  const [replaySessionId, setReplaySessionId] = useState<string | null>(null);

  const [lastError, setLastError] = useState<string | null>(null);

  const activeSockets = useRef<Array<() => void>>([]);
  useEffect(() => () => activeSockets.current.forEach((close) => close()), []);

  useEffect(() => {
    api
      .request<PersonaRecord[]>("/personas")
      .then(setPersonas)
      .catch(() => {});
  }, [api]);

  // Only offer environments the selected project actually defines — any
  // other choice is a guaranteed 400 from the API.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    fetchProject(api, projectId)
      .then((detail) => {
        if (!cancelled) setProjectEnvs({ projectId, names: Object.keys(detail.config.environments ?? {}) });
      })
      .catch(() => {
        if (!cancelled) setProjectEnvs({ projectId, names: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [api, projectId]);
  const environments = projectId && projectEnvs?.projectId === projectId ? projectEnvs.names : [];
  const selectedEnvironment = environments.includes(environment)
    ? environment
    : environments.includes("dev")
      ? "dev"
      : (environments[0] ?? "");

  // A batch is busy until every member has a verdict — derived from member
  // state, not toggled from inside a setState updater.
  const batchBusy = isBatchMode && (batchStarting || batchMembers.some((m) => m.phase.kind !== "finished"));
  const busy = running || batchBusy;

  const isBatch = selectedPersonaIds.size > 1;

  function togglePersona(id: string) {
    setSelectedPersonaIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function startRun() {
    setIsBatchMode(false);
    setLiveSteps([]);
    setRunning(true);
    setPhase({ kind: "running" });
    setLastError(null);

    try {
      const started = await api.request<RunStarted>("/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          persona_id: [...selectedPersonaIds][0] ?? "",
          objective,
          environment: selectedEnvironment,
          headed,
          step_through: stepThrough,
          caller: "suth-web",
        }),
      });
      setCurrentSessionId(started.session_id);
      watchSteps(started.session_id, stepThrough);
    } catch (err) {
      setLastError(err instanceof Error ? err.message : String(err));
      setRunning(false);
      setPhase({ kind: "idle" });
    }
  }

  function watchSteps(sessionId: string, stepThroughMode: boolean) {
    const cancel = watchSession(
      api,
      sessionId,
      (event) => {
        setLiveSteps((prev) => [...prev, event]);
        setStepThroughWaiting(stepThroughMode);
      },
      () => finishRun(sessionId)
    );
    activeSockets.current.push(cancel);
  }

  async function finishRun(sessionId: string) {
    setStepThroughWaiting(false);
    try {
      const report = await api.request<RunReport>(`/runs/${sessionId}/report`);
      setPhase({ kind: "finished", verdict: report.verdict });
    } catch (err) {
      setLastError(err instanceof Error ? err.message : String(err));
      setPhase({ kind: "idle" });
    }
    setRunning(false);
  }

  function continueStep() {
    if (!currentSessionId) return;
    setStepThroughWaiting(false);
    api
      .request(`/runs/${currentSessionId}/continue`, { method: "POST" })
      .catch((err) => setLastError(err instanceof Error ? err.message : String(err)));
  }

  async function startBatch() {
    setIsBatchMode(true);
    setBatchMembers([]);
    setBatchStarting(true);
    setPhase({ kind: "idle" });
    setLastError(null);

    try {
      const started = await api.request<BatchStarted>("/batches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          persona_ids: [...selectedPersonaIds],
          objective,
          environment: selectedEnvironment,
          headed,
          caller: "suth-web",
        }),
      });

      const members: BatchMember[] = started.sessions.map((s) => ({
        sessionId: s.session_id,
        personaId: s.persona_id,
        steps: [],
        phase: { kind: "running" },
      }));
      setBatchMembers(members);

      members.forEach((member) => watchBatchMember(member.sessionId));
    } catch (err) {
      setLastError(err instanceof Error ? err.message : String(err));
    } finally {
      setBatchStarting(false);
    }
  }

  function updateMember(sessionId: string, update: (m: BatchMember) => BatchMember) {
    setBatchMembers((prev) => prev.map((m) => (m.sessionId === sessionId ? update(m) : m)));
  }

  function watchBatchMember(sessionId: string) {
    const cancel = watchSession(
      api,
      sessionId,
      (event) => updateMember(sessionId, (m) => ({ ...m, steps: [...m.steps, event] })),
      () => {
        api
          .request<RunReport>(`/runs/${sessionId}/report`)
          .then((report) => updateMember(sessionId, (m) => ({ ...m, phase: { kind: "finished", verdict: report.verdict } })))
          .catch(() => updateMember(sessionId, (m) => ({ ...m, phase: { kind: "finished", verdict: "error" } })));
      }
    );
    activeSockets.current.push(cancel);
  }

  const canRun =
    projectId !== "" && selectedPersonaIds.size > 0 && objective !== "" && selectedEnvironment !== "" && !busy;

  return (
    <>
      <PageHeader
        eyebrow="Harness"
        title="Run"
        description="Point a persona at an objective and watch the live transcript. Select more than one persona to fan out as a batch."
        actions={
          <>
            {!isBatch && <StatusBadge phase={phase} />}
            {!isBatch && stepThroughWaiting && (
              <button type="button" onClick={continueStep}>
                Continue step
              </button>
            )}
            {!isBatch && phase.kind === "finished" && currentSessionId && (
              <button type="button" onClick={() => setReplaySessionId(currentSessionId)}>
                Watch replay
              </button>
            )}
            <button type="button" className="primary" disabled={!canRun} onClick={isBatch ? startBatch : startRun}>
              {busy ? "Running…" : isBatch ? `Run batch (${selectedPersonaIds.size})` : "Run"}
            </button>
          </>
        }
      />

      <div className="split">
        <section className="panel">
          <div className="panel-head">
            <h2>Setup</h2>
            {isBatch ? <span className="badge">{selectedPersonaIds.size} personas</span> : null}
          </div>
          <div className="panel-body stack">
            {!projectId ? (
              <p className="field-hint">Select a project in the header to run against a target app.</p>
            ) : null}

            <div className="field">
              <span className="field-label">Personas</span>
              <p className="field-hint">Select more than one to run in parallel.</p>
              <div className="chips">
                {personas.length === 0 ? (
                  <span className="muted">No personas loaded.</span>
                ) : (
                  personas.map((p) => {
                    const selected = selectedPersonaIds.has(p.id);
                    return (
                      <label key={p.id} className={selected ? "chip selected" : "chip"}>
                        <input type="checkbox" checked={selected} onChange={() => togglePersona(p.id)} />
                        {p.name ?? p.id}
                      </label>
                    );
                  })
                )}
              </div>
            </div>

            <div className="field">
              <label htmlFor="run-objective">Objective</label>
              <textarea
                id="run-objective"
                rows={2}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="What should the persona try to accomplish?"
              />
            </div>

            <div className="row stretch">
              <div className="field">
                <label htmlFor="run-env">Environment</label>
                <select
                  id="run-env"
                  value={selectedEnvironment}
                  disabled={environments.length === 0}
                  onChange={(e) => setEnvironment(e.target.value)}
                >
                  {environments.length === 0 ? (
                    <option value="">{projectId ? "No environments defined" : "Select a project"}</option>
                  ) : (
                    environments.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>

            <div className="row">
              <label className="switch">
                <input type="checkbox" checked={headed} onChange={(e) => setHeaded(e.target.checked)} />
                Headed browser
              </label>
              {!isBatch && (
                <label className="switch">
                  <input type="checkbox" checked={stepThrough} onChange={(e) => setStepThrough(e.target.checked)} />
                  Step-through
                </label>
              )}
            </div>

            {lastError && <p className="error-text">{lastError}</p>}
          </div>
        </section>

        {isBatchMode ? (
          <section className="panel grow">
            <div className="panel-head">
              <h2>Batch</h2>
              <span className="muted">{batchMembers.filter((m) => m.phase.kind === "finished").length}/{batchMembers.length} done</span>
            </div>
            <div className="panel-body">
              {batchMembers.length === 0 ? (
                <div className="empty">
                  <strong>Starting batch</strong>
                  Waiting for sessions to appear.
                </div>
              ) : (
                <div className="grid">
                  {batchMembers.map((member) => (
                    <BatchMemberCard key={member.sessionId} member={member} onClick={() => setDetailMemberId(member.sessionId)} />
                  ))}
                </div>
              )}
            </div>
          </section>
        ) : (
          <section className="panel grow">
            <div className="panel-head">
              <h2>Live transcript</h2>
              {liveSteps.length > 0 ? <span className="muted">{liveSteps.length} steps</span> : null}
            </div>
            <div className="panel-body">
              {liveSteps.length === 0 ? (
                <div className="empty">
                  <strong>Nothing running yet</strong>
                  Choose a project, persona, and objective, then start a run.
                </div>
              ) : (
                <div className="transcript-scroll">
                  {liveSteps.map((step) => (
                    <StepRow key={step.step_index} step={step} sessionId={currentSessionId} />
                  ))}
                </div>
              )}
            </div>
          </section>
        )}
      </div>

      {detailMember && (
        <div className="modal-backdrop" onClick={() => setDetailMemberId(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{detailMember.personaId}</h3>
              <div className="row">
                {detailMember.phase.kind === "finished" && (
                  <button
                    type="button"
                    onClick={() => {
                      setReplaySessionId(detailMember.sessionId);
                      setDetailMemberId(null);
                    }}
                  >
                    Watch replay
                  </button>
                )}
                <button type="button" className="ghost" onClick={() => setDetailMemberId(null)}>
                  Close
                </button>
              </div>
            </div>
            <div className="transcript-scroll" style={{ maxHeight: "60vh" }}>
              {detailMember.steps.map((step) => (
                <StepRow key={step.step_index} step={step} sessionId={detailMember.sessionId} />
              ))}
            </div>
          </div>
        </div>
      )}

      {replaySessionId && (
        <SessionReplay sessionId={replaySessionId} onClose={() => setReplaySessionId(null)} />
      )}
    </>
  );
}

function StatusBadge({ phase }: { phase: RunPhase }) {
  if (phase.kind === "idle") return null;
  if (phase.kind === "running")
    return (
      <span className="badge running">
        <Loader2 className="spin" size={11} aria-hidden="true" />
        {formatVerdict("running")}
      </span>
    );
  const ok = phase.verdict === VERDICT_OK;
  return <span className={`badge ${ok ? "ok" : "bad"}`}>{formatVerdict(phase.verdict)}</span>;
}

function BatchMemberCard({ member, onClick }: { member: BatchMember; onClick: () => void }) {
  return (
    <div className="panel member-card" onClick={onClick}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b>{member.personaId}</b>
        <MemberBadge phase={member.phase} />
      </div>
      <p className="muted" style={{ margin: "0.45rem 0 0.35rem" }}>
        {member.steps.at(-1)?.thought ?? "Waiting for the first step…"}
      </p>
      <p className="muted" style={{ margin: 0, fontSize: "0.75rem" }}>
        {member.steps.length} steps
      </p>
    </div>
  );
}

function MemberBadge({ phase }: { phase: RunPhase }) {
  if (phase.kind === "idle") return null;
  if (phase.kind === "running")
    return (
      <span className="badge running">
        <Loader2 className="spin" size={11} aria-hidden="true" />
        live
      </span>
    );
  const ok = phase.verdict === VERDICT_OK;
  return <span className={`badge ${ok ? "ok" : "bad"}`}>{ok ? "passed" : "failed"}</span>;
}
