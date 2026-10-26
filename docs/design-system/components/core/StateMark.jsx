import React from "react";
import { stateMeta } from "./hooks.js";
export function StateMark({ state, size = 14, withLabel = false, label, style }) {
  const m = stateMeta[state] || { tone: "outside", label: "Reference" };
  const c = state === "reference" ? "var(--ink-subtle)" : "var(--state-" + m.tone + ")";
  const r = size / 2 - 1.25, cx = size / 2;
  let g;
  if (m.tone === "observed") g = <circle cx={cx} cy={cx} r={r} fill={c} />;
  else if (m.tone === "not-observed") g = <circle cx={cx} cy={cx} r={r - 0.5} fill="none" stroke={c} strokeWidth="2" />;
  else if (m.tone === "array-gap") g = <circle cx={cx} cy={cx} r={r - 0.5} fill="none" stroke={c} strokeWidth="1.75" strokeDasharray="2.4 2" />;
  else if (m.tone === "insufficient") g = <g><circle cx={cx} cy={cx} r={r - 0.5} fill="none" stroke={c} strokeWidth="1.75" /><path d={"M" + cx + " " + (cx - r + 0.5) + " A" + (r - 0.5) + " " + (r - 0.5) + " 0 0 0 " + cx + " " + (cx + r - 0.5) + " Z"} fill={c} /></g>;
  else g = <circle cx={cx} cy={cx} r={size / 5} fill={c} />;
  const svg = <svg width={size} height={size} viewBox={"0 0 " + size + " " + size} aria-hidden={withLabel ? true : undefined} role={withLabel ? undefined : "img"} aria-label={withLabel ? undefined : (label || m.label)} style={{ flex: "none", display: "block" }}>{g}</svg>;
  if (!withLabel) return svg;
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 8, font: "700 14px var(--font-sans)", color: "var(--text-body)", whiteSpace: "nowrap", ...style }}>{svg}{label || m.label}</span>;
}
