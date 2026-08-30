"use client";

import type { CSSProperties } from "react";
import { useMemo, useRef, useState } from "react";
import {
  formatAxisDate,
  formatVerdict,
  formatWhen,
  frictionColor,
  verdictTone,
  type TrendPoint,
} from "@/lib/format";

export type { TrendPoint };

/** Friction-score trend line with chronological dates along the X-axis. */
export function Sparkline({
  data,
  values,
}: {
  data?: TrendPoint[];
  values?: number[];
}) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const points: TrendPoint[] = useMemo(() => {
    if (data && data.length > 0) return data;
    if (values && values.length > 0) return values.map((v) => ({ score: v }));
    return [];
  }, [data, values]);

  const ticks = useMemo(() => {
    const n = points.length;
    if (n < 2) return [];
    let indices: number[] = [];
    if (n <= 5) {
      indices = Array.from({ length: n }, (_, i) => i);
    } else {
      indices = [
        0,
        Math.round((n - 1) * 0.25),
        Math.round((n - 1) * 0.5),
        Math.round((n - 1) * 0.75),
        n - 1,
      ];
      indices = Array.from(new Set(indices));
    }

    return indices.map((idx) => {
      const p = points[idx];
      const pct = (idx / (n - 1)) * 100;
      const label = p.started_at ? formatAxisDate(p.started_at) : `Run #${idx + 1}`;
      return { index: idx, pct, label };
    });
  }, [points]);

  if (points.length < 2) {
    return <p className="sparkline-empty muted">Need at least two scored data points to chart friction.</p>;
  }

  const scores = points.map((p) => p.score);
  const maxScore = Math.max(...scores, 1);
  const yMax = Math.max(Math.ceil(maxScore), 2);

  const svgWidth = 1000;
  const svgHeight = 90;
  const paddingTop = 12;
  const paddingBottom = 12;
  const plotHeight = svgHeight - paddingTop - paddingBottom;

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * svgWidth;
    const y = paddingTop + plotHeight - (p.score / yMax) * plotHeight;
    return { x, y, point: p, index: i };
  });

  const polyline = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const area = `M 0,${svgHeight - paddingBottom} L ${polyline.replace(/ /g, " L ")} L ${svgWidth},${svgHeight - paddingBottom} Z`;

  const activeCoord = hoveredIdx !== null ? coords[hoveredIdx] : null;

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || points.length < 2) return;
    const clientX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clientX / rect.width));
    const closestIdx = Math.round(pct * (points.length - 1));
    setHoveredIdx(closestIdx);
  }

  return (
    <div
      className="trend-chart-container"
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoveredIdx(null)}
    >
      <div className="trend-plot-area">
        <svg
          className="trend-svg"
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Friction score trend"
        >
          <defs>
            <linearGradient id="trend-area-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--red)" stopOpacity={0.22} />
              <stop offset="100%" stopColor="var(--red)" stopOpacity={0.02} />
            </linearGradient>
          </defs>

          {/* Horizontal gridlines */}
          <line
            x1="0"
            y1={paddingTop}
            x2={svgWidth}
            y2={paddingTop}
            stroke="var(--border)"
            strokeDasharray="4 4"
            strokeWidth="1"
            opacity="0.6"
          />
          <line
            x1="0"
            y1={paddingTop + plotHeight / 2}
            x2={svgWidth}
            y2={paddingTop + plotHeight / 2}
            stroke="var(--border)"
            strokeDasharray="4 4"
            strokeWidth="1"
            opacity="0.6"
          />
          <line
            x1="0"
            y1={svgHeight - paddingBottom}
            x2={svgWidth}
            y2={svgHeight - paddingBottom}
            stroke="var(--border-strong)"
            strokeWidth="1"
          />

          {/* Area & Polyline */}
          <path d={area} fill="url(#trend-area-grad)" />
          <polyline
            points={polyline}
            fill="none"
            stroke="var(--red)"
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Point dots */}
          {coords.map((c) => (
            <circle
              key={c.index}
              cx={c.x}
              cy={c.y}
              r={hoveredIdx === c.index ? 5 : 3}
              className={`trend-dot ${hoveredIdx === c.index ? "active" : ""}`}
            />
          ))}

          {/* Active crosshair */}
          {activeCoord && (
            <line
              x1={activeCoord.x}
              y1={paddingTop}
              x2={activeCoord.x}
              y2={svgHeight - paddingBottom}
              stroke="var(--fg)"
              strokeWidth="1"
              strokeDasharray="2 2"
              opacity="0.4"
            />
          )}
        </svg>

        {/* Hover Tooltip */}
        {activeCoord && activeCoord.point && (
          <div
            className="trend-tooltip"
            style={{
              left: `${(activeCoord.index / (points.length - 1)) * 100}%`,
              transform:
                activeCoord.index === 0
                  ? "translate(0, -100%)"
                  : activeCoord.index === points.length - 1
                    ? "translate(-100%, -100%)"
                    : "translate(-50%, -100%)",
            }}
          >
            <div className="trend-tooltip-head">
              <span className="mono">
                {activeCoord.point.started_at
                  ? formatWhen(activeCoord.point.started_at)
                  : `Point #${activeCoord.index + 1}`}
              </span>
              <div className="row" style={{ gap: "0.35rem" }}>
                {activeCoord.point.runs && activeCoord.point.runs.length > 1 && (
                  <span className="muted" style={{ fontSize: "0.72rem" }}>
                    avg
                  </span>
                )}
                <span
                  className="friction-score mono"
                  style={{ "--friction-color": frictionColor(activeCoord.point.score) } as CSSProperties}
                >
                  {activeCoord.point.score.toFixed(1)}
                </span>
              </div>
            </div>

            {activeCoord.point.runs && activeCoord.point.runs.length > 1 ? (
              <div className="trend-tooltip-runs">
                <div className="trend-tooltip-runs-label muted">
                  {activeCoord.point.runs.length} runs in batch:
                </div>
                {activeCoord.point.runs.map((r, i) => (
                  <div key={r.id || i} className="trend-tooltip-run-row">
                    <span className="trend-tooltip-persona">{r.persona_id}</span>
                    <div className="row" style={{ gap: "0.35rem" }}>
                      {r.verdict && (
                        <span
                          className={`badge ${verdictTone(r.verdict)}`}
                          style={{ fontSize: "0.68rem", padding: "0.05rem 0.4rem" }}
                        >
                          {formatVerdict(r.verdict)}
                        </span>
                      )}
                      <span className="mono" style={{ fontSize: "0.75rem", color: frictionColor(r.score) }}>
                        {r.score.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              (activeCoord.point.persona_id || activeCoord.point.verdict) && (
                <div className="trend-tooltip-meta">
                  {activeCoord.point.persona_id && (
                    <span className="trend-tooltip-persona">{activeCoord.point.persona_id}</span>
                  )}
                  {activeCoord.point.verdict && (
                    <span className={`badge ${verdictTone(activeCoord.point.verdict)}`}>
                      {formatVerdict(activeCoord.point.verdict)}
                    </span>
                  )}
                </div>
              )
            )}
          </div>
        )}
      </div>

      {/* X-axis with date labels */}
      <div className="trend-x-axis">
        {ticks.map(({ index, pct, label }) => (
          <div
            key={index}
            className="trend-x-tick"
            style={{
              left: `${pct}%`,
              transform:
                index === 0
                  ? "translateX(0%)"
                  : index === points.length - 1
                    ? "translateX(-100%)"
                    : "translateX(-50%)",
            }}
          >
            <span className="trend-x-tick-mark" />
            <span className="trend-x-date mono">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
