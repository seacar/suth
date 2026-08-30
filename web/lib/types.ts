// Mirrors gui/Sources/SuthGUI/Models.swift — the shapes returned by the
// Local Control API (src/suth/api/app.py).

export interface PersonaRecord {
  id: string;
  name: string | null;
  version: number;
}

export interface ProjectRecord {
  id: string;
  name: string;
  base_url: string;
  config_path?: string;
  config_dir?: string;
}

export interface SuthConfigRecord {
  project_id: string;
  base_url: string;
  default_personas: string[];
  environments: Record<
    string,
    {
      base_url?: string | null;
      headed?: boolean | null;
      headless?: boolean | null;
      model?: string | null;
      max_steps?: number | null;
      timeout_seconds?: number | null;
      token_cap?: number | null;
      record_video?: boolean | null;
    }
  >;
  llm_providers: Record<
    string,
    {
      provider: string;
      model: string;
      base_url?: string | null;
      credential?: string | null;
    }
  >;
  auth?: { type: string; path: string } | null;
}

export interface BrowseEntry {
  name: string;
  path: string;
  kind: "dir" | "file";
}

export interface BrowseResponse {
  path: string;
  abs_path: string;
  parent: string | null;
  entries: BrowseEntry[];
  config_exists: boolean;
}

export interface ConfigAtResponse {
  config_dir: string;
  config_path: string;
  exists: boolean;
  config: SuthConfigRecord | null;
  provider_credentials_configured?: Record<string, boolean>;
}

export interface ProjectDetail extends ProjectRecord {
  config: SuthConfigRecord;
  provider_credentials_configured?: Record<string, boolean>;
}

export interface RunRequest {
  project_id: string;
  persona_id: string;
  objective: string;
  environment: string;
  headed?: boolean;
  step_through: boolean;
  caller?: string;
}

export interface RunStarted {
  session_id: string;
  status: string;
}

export interface BatchRequest {
  project_id: string;
  persona_ids: string[];
  objective: string;
  environment: string;
  headed?: boolean;
  caller?: string;
}

export interface BatchMemberStarted {
  session_id: string;
  persona_id: string;
}

export interface BatchStarted {
  batch_id: string;
  sessions: BatchMemberStarted[];
}

export interface FailureHit {
  taxonomy_label: string;
  step_index: number;
  detail: string | null;
}

export interface RunReport {
  session_id: string;
  verdict: string;
  step_count: number;
  final_frustration: number;
  friction_score: number;
  failures: FailureHit[];
}

export interface SessionRow {
  id: string;
  project_id: string;
  persona_id: string;
  objective: string;
  environment: string;
  status: string;
  verdict: string | null;
  friction_score: number | null;
  started_at: string;
  ended_at: string | null;
  caller: string | null;
  video_ref?: string | null;
  video_started_at?: string | null;
  video_duration_seconds?: number | null;
}

export interface ComparisonResult {
  baseline_session_id: string;
  candidate_session_id: string;
  baseline_friction_score: number;
  candidate_friction_score: number;
  friction_delta: number;
  baseline_taxonomy_counts: Record<string, number>;
  candidate_taxonomy_counts: Record<string, number>;
  regressed: boolean;
}

export interface StepEvent {
  type: "step" | "done";
  step_index: number;
  thought?: string | null;
  action_type?: string | null;
  target?: string | null;
  dom_changed?: boolean | null;
  url?: string | null;
  emotion?: string | null;
  frustration_delta?: number | null;
  screenshot_ref?: string | null;
}

export interface GlobalEvent {
  type: string;
  session_id: string;
  project_id: string;
  verdict: string | null;
  friction_score: number | null;
  caller: string | null;
}

export interface TranscriptStep {
  step_index: number;
  thought: string;
  emotion: string;
  frustration_delta: number;
  action_jsonb: { type?: string; target?: string; [key: string]: unknown };
  dom_snapshot_ref: string | null;
  screenshot_ref: string | null;
  created_at?: string;
  /** Seconds into the replay video this step's screenshot was captured —
   * null if the session has no video. */
  offset_seconds?: number | null;
}

export interface TranscriptFailure {
  taxonomy_label: string;
  step_index: number;
  detail: string | null;
}

export interface Transcript {
  session: SessionRow;
  steps: TranscriptStep[];
  failures: TranscriptFailure[];
}

export type RunPhase = { kind: "idle" } | { kind: "running" } | { kind: "finished"; verdict: string };

export interface BatchMember {
  sessionId: string;
  personaId: string;
  steps: StepEvent[];
  phase: RunPhase;
}
