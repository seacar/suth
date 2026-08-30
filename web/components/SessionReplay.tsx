"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "@/lib/api-context";
import { formatVerdict } from "@/lib/format";
import type { Transcript, TranscriptFailure, TranscriptStep } from "@/lib/types";

const SPEEDS = [0.5, 1, 1.5, 2];

const EMOTION_EMOJI: Record<string, string> = {
  neutral: "\u{1F610}",
  confused: "\u{1F615}",
  frustrated: "\u{1F624}",
  annoyed: "\u{1F620}",
  satisfied: "\u{1F642}",
  delighted: "\u{1F60A}",
};

function fmtTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Full replay experience for one session — video player (synced via each
 * step's `offset_seconds`, computed server-side against when Playwright
 * started recording) plus a clickable transcript that highlights in step
 * with playback and lets you jump the video by clicking any step. */
export function SessionReplay({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const api = useApi();
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  const videoRef = useRef<HTMLVideoElement>(null);
  const activeStepRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .request<Transcript>(`/runs/${sessionId}/transcript`)
      .then(setTranscript)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [api, sessionId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") return onClose();
      const video = videoRef.current;
      if (!video) return;
      if (e.key === " ") {
        e.preventDefault();
        if (video.paused) video.play();
        else video.pause();
      } else if (e.key === "ArrowRight") {
        seekToStep(1);
      } else if (e.key === "ArrowLeft") {
        seekToStep(-1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transcript, currentTime]);

  useEffect(() => {
    activeStepRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [currentTime]);

  const steps = useMemo(() => transcript?.steps ?? [], [transcript]);
  const hasVideo = Boolean(transcript?.session.video_ref);
  const timedSteps = useMemo(
    () => steps.filter((s): s is TranscriptStep & { offset_seconds: number } => s.offset_seconds != null),
    [steps]
  );

  const activeStepIndex = useMemo(() => {
    let active: number | null = null;
    for (const s of timedSteps) {
      if (s.offset_seconds <= currentTime + 0.15) active = s.step_index;
      else break;
    }
    return active;
  }, [timedSteps, currentTime]);

  function seekTo(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, Math.min(seconds, duration || seconds));
  }

  function seekToStep(direction: 1 | -1) {
    if (timedSteps.length === 0) return;
    const idx = timedSteps.findIndex((s) => s.step_index === activeStepIndex);
    const nextIdx = Math.max(0, Math.min(timedSteps.length - 1, (idx < 0 ? 0 : idx) + direction));
    seekTo(timedSteps[nextIdx].offset_seconds);
  }

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) video.play();
    else video.pause();
  }

  function changeSpeed(next: number) {
    setSpeed(next);
    if (videoRef.current) videoRef.current.playbackRate = next;
  }

  if (error) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <p className="error-text">{error}</p>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    );
  }

  if (!transcript) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal replay-modal">
          <p className="muted">Loading replay…</p>
        </div>
      </div>
    );
  }

  const { session, failures } = transcript;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal replay-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>{session.persona_id}</h3>
            <p className="muted" style={{ margin: "0.2rem 0 0", fontSize: "0.82rem" }}>
              {session.project_id} &middot; &ldquo;{session.objective}&rdquo;
            </p>
          </div>
          <div className="row">
            <VerdictBadge verdict={session.verdict} friction={session.friction_score} />
            <button type="button" className="ghost" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        <div className="replay-body">
          <div className="replay-player">
            {hasVideo ? (
              <>
                <video
                  ref={videoRef}
                  src={api.videoUrl(session.id)}
                  className="replay-video"
                  onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                  onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                />
                <ReplayTimeline
                  duration={duration}
                  currentTime={currentTime}
                  steps={timedSteps}
                  failures={failures}
                  onSeek={seekTo}
                />
                <div className="replay-controls">
                  <button onClick={togglePlay} className="primary">
                    {playing ? "Pause" : "Play"}
                  </button>
                  <button onClick={() => seekToStep(-1)} title="Previous step (←)">
                    ◀ step
                  </button>
                  <button onClick={() => seekToStep(1)} title="Next step (→)">
                    step ▶
                  </button>
                  <span className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {fmtTime(currentTime)} / {fmtTime(duration)}
                  </span>
                  <span className="row" style={{ gap: "0.25rem", marginLeft: "auto" }}>
                    {SPEEDS.map((s) => (
                      <button
                        key={s}
                        className={speed === s ? "primary" : ""}
                        style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => changeSpeed(s)}
                      >
                        {s}x
                      </button>
                    ))}
                  </span>
                </div>
              </>
            ) : (
              <div className="replay-novideo muted">
                No replay video for this session (recorded before video capture was added, or
                <code> record_video: false</code> for its environment).
              </div>
            )}

            {failures.length > 0 && (
              <div className="replay-failures">
                <h4 style={{ margin: "0.75rem 0 0.3rem", fontSize: "0.85rem" }}>failures</h4>
                {failures.map((f) => (
                  <div key={`${f.step_index}-${f.taxonomy_label}`} className="muted" style={{ fontSize: "0.8rem" }}>
                    step {f.step_index}: <b>{f.taxonomy_label}</b> {f.detail ? `— ${f.detail}` : ""}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="replay-transcript transcript-scroll">
            {steps.map((s) => (
              <div
                key={s.step_index}
                ref={s.step_index === activeStepIndex ? activeStepRef : null}
                className={`replay-step ${s.step_index === activeStepIndex ? "active" : ""}`}
                onClick={() => s.offset_seconds != null && seekTo(s.offset_seconds)}
                style={{ cursor: s.offset_seconds != null ? "pointer" : "default" }}
              >
                <div className="row" style={{ gap: "0.4rem" }}>
                  <span className="muted">#{s.step_index}</span>
                  {s.emotion ? <span className="emotion-badge">{EMOTION_EMOJI[s.emotion] ?? s.emotion}</span> : null}
                  {s.offset_seconds != null && (
                    <span className="muted" style={{ fontSize: "0.75rem" }}>
                      {fmtTime(s.offset_seconds)}
                    </span>
                  )}
                </div>
                <div>&ldquo;{s.thought}&rdquo;</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  {s.action_jsonb?.type ?? ""} {s.action_jsonb?.target ? `on ${s.action_jsonb.target}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function VerdictBadge({ verdict, friction }: { verdict: string | null; friction: number | null }) {
  if (!verdict)
    return (
      <span className="badge running">
        <Loader2 className="spin" size={11} aria-hidden="true" />
        {formatVerdict("running")}
      </span>
    );
  const ok = verdict === "objective_met";
  return (
    <span className={`badge ${ok ? "ok" : "bad"}`}>
      {formatVerdict(verdict)} {friction !== null ? `(${friction.toFixed(1)})` : ""}
    </span>
  );
}

function ReplayTimeline({
  duration,
  currentTime,
  steps,
  failures,
  onSeek,
}: {
  duration: number;
  currentTime: number;
  steps: (TranscriptStep & { offset_seconds: number })[];
  failures: TranscriptFailure[];
  onSeek: (seconds: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const failureSteps = new Set(failures.map((f) => f.step_index));

  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    const track = trackRef.current;
    if (!track || !duration) return;
    const rect = track.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    onSeek(pct * duration);
  }

  const progressPct = duration ? (currentTime / duration) * 100 : 0;

  return (
    <div className="replay-timeline" ref={trackRef} onClick={handleClick}>
      <div className="replay-timeline-fill" style={{ width: `${progressPct}%` }} />
      {duration > 0 &&
        steps.map((s) => (
          <div
            key={s.step_index}
            className={`replay-tick ${failureSteps.has(s.step_index) ? "failure" : ""}`}
            style={{ left: `${(s.offset_seconds / duration) * 100}%` }}
            title={`#${s.step_index} — ${fmtTime(s.offset_seconds)}`}
          />
        ))}
    </div>
  );
}
