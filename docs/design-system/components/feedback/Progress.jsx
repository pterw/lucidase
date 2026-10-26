import React from "react";
export function Progress({ value = 0, label, showValue = true, style }) {
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, ...style }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, font: "400 15px var(--font-sans)", color: "var(--text-body)" }}>
        <span aria-live="polite">{label}</span>{showValue && <span style={{ font: "700 14px var(--font-mono)" }}>{Math.round(v)}%</span>}
      </div>
      <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v)} aria-label={typeof label === "string" ? label : "Progress"} style={{ height: 3, background: "var(--line)", overflow: "hidden" }}>
        <div style={{ width: "100%", height: "100%", background: "var(--ink)", transform: "scaleX(" + v / 100 + ")", transformOrigin: "left", transition: "transform var(--dur-fast) linear" }} />
      </div>
    </div>
  );
}
