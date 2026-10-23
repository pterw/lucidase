import React from "react";
import { NotAvailable } from "../feedback/NotAvailable.jsx";
export function ProbabilityBar({ label, value, tone = "observed", detail }) {
  const missing = value === null || value === undefined;
  const v = missing ? 0 : Math.max(0, Math.min(100, value));
  const c = ["observed","not-observed","array-gap","outside","insufficient"].indexOf(tone) >= 0 ? "var(--state-" + tone + ")" : "var(--cat-" + tone + "-ink)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, font: "400 14px var(--font-sans)", color: "var(--text-body)" }}>
        <span>{label}</span>
        <span style={{ font: "700 14px var(--font-mono)" }}>{missing ? <NotAvailable /> : (Math.round(v * 10) / 10) + "%"}{detail && <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>{" " + detail}</span>}</span>
      </div>
      <div style={{ height: 6, background: "var(--line)", overflow: "hidden" }}><div style={{ width: "100%", height: "100%", background: c, transform: "scaleX(" + v / 100 + ")", transformOrigin: "left", transition: "transform var(--dur-slow) var(--ease-standard)" }} /></div>
    </div>
  );
}
