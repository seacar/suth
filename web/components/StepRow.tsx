"use client";

import { useApi } from "@/lib/api-context";
import type { StepEvent } from "@/lib/types";

/** One live step in a transcript — thought, action, emotion badge, 5-bar
 * frustration meter, screenshot thumbnail. Mirrors StepRow in RunView.swift. */
export function StepRow({ step, sessionId }: { step: StepEvent; sessionId: string | null }) {
  const { screenshotUrl } = useApi();

  return (
    <div className="step-row">
      {sessionId && step.screenshot_ref ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="step-thumb" src={screenshotUrl(sessionId, step.step_index)} alt="" />
      ) : null}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ gap: "0.4rem" }}>
          <span className="muted mono">#{step.step_index}</span>
          {step.emotion ? <span className="emotion-badge">{step.emotion}</span> : null}
          <FrustrationMeter delta={step.frustration_delta ?? null} />
        </div>
        <div>&#8220;{step.thought ?? ""}&#8221;</div>
        <div className="muted" style={{ fontSize: "0.8rem" }}>
          {step.action_type ?? ""} {step.target ?? ""}
        </div>
      </div>
    </div>
  );
}

function FrustrationMeter({ delta }: { delta: number | null }) {
  if (delta === null) return null;
  return (
    <span className="meter">
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < delta ? "filled" : ""} />
      ))}
    </span>
  );
}
