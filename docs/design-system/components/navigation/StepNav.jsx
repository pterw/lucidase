import React, { useRef } from "react";
import { useWidth } from "../core/hooks.js";
export function StepNav({ steps, current, onStep, label = "Steps", breakpoint = 560 }) {
  const ref = useRef(null); const w = useWidth(ref);
  if (w < breakpoint) {
    const pct = ((current + 1) / steps.length) * 100;
    return (
      <nav ref={ref} aria-label={label} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
          <span aria-current="step" style={{ font: "700 15px var(--font-sans)" }}>{steps[current].label}</span>
          <span style={{ font: "400 13px var(--font-mono)", color: "var(--text-muted)" }}>Step {current + 1} of {steps.length}</span>
        </div>
        <div aria-hidden="true" style={{ height: 3, background: "var(--line)" }}><div style={{ height: "100%", width: "100%", background: "var(--ink)", transform: "scaleX(" + pct / 100 + ")", transformOrigin: "left", transition: "transform var(--dur-slow) var(--ease-standard)" }} /></div>
        {onStep && current > 0 && <button type="button" onClick={() => onStep(current - 1)} style={{ alignSelf: "flex-start", minHeight: 32, padding: 0, border: 0, background: "none", font: "700 14px var(--font-sans)", color: "var(--text-link)", cursor: "pointer" }}>← {steps[current - 1].label}</button>}
      </nav>
    );
  }
  return (
    <nav ref={ref} aria-label={label}>
      <ol style={{ display: "flex", alignItems: "center", gap: 0, margin: 0, padding: 0, listStyle: "none" }}>
        {steps.map((s, i) => {
          const state = i < current ? "done" : i === current ? "now" : "next";
          const can = onStep && s.enabled !== false && state !== "now";
          const dot = <span aria-hidden="true" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 24, height: 24, flex: "none", borderRadius: "var(--radius-dot)", font: "700 12px var(--font-mono)", background: state === "now" ? "var(--ink)" : "transparent", color: state === "now" ? "var(--on-ink)" : state === "done" ? "var(--text-body)" : "var(--text-subtle)", border: "1.5px solid " + (state === "next" ? "var(--border-strong)" : "var(--ink)") }}>{state === "done" ? "✓" : i + 1}</span>;
          const txt = <span style={{ whiteSpace: "nowrap" }}>{s.label}{state === "done" && <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}> (done)</span>}</span>;
          const base = { display: "inline-flex", alignItems: "center", gap: 8, minHeight: 44, font: "700 14px var(--font-sans)" };
          return (
            <li key={i} style={{ display: "flex", alignItems: "center", flex: i < steps.length - 1 ? "1 1 auto" : "none", minWidth: 0 }}>
              {can ? <button type="button" onClick={() => onStep(i)} style={{ ...base, border: 0, background: "none", padding: 0, cursor: "pointer", color: "var(--text-body)" }}>{dot}{txt}</button>
                : <span aria-current={state === "now" ? "step" : undefined} style={{ ...base, color: state === "next" ? "var(--text-subtle)" : "var(--text-body)" }}>{dot}{txt}</span>}
              {i < steps.length - 1 && <span aria-hidden="true" style={{ flex: 1, minWidth: 16, height: 1, margin: "0 14px", background: i < current ? "var(--ink)" : "var(--border-strong)" }} />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
