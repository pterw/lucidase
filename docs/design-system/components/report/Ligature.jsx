import React from "react";
export function Ligature({ left, right, result, caption }) {
  return (
    <figure style={{ margin: 0, display: "inline-flex", flexDirection: "column", gap: 4 }}>
      <svg viewBox="0 0 240 34" width="240" height="34" aria-hidden="true" style={{ display: "block" }}>
        <path d="M30 32 C 30 4, 210 4, 210 32" fill="none" stroke="var(--ink)" strokeWidth="1.5" />
        <circle cx="120" cy="11" r="4" fill="var(--accent)" />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", width: 240, font: "400 13px var(--font-mono)", color: "var(--text-muted)" }}><span>{left}</span><span>{right}</span></div>
      {result && <div style={{ width: 240, textAlign: "center", font: "400 22px/1.2 var(--font-serif)", color: "var(--text-body)" }}>{result}</div>}
      {caption && <figcaption style={{ width: 240, textAlign: "center", font: "400 13px var(--font-sans)", color: "var(--text-muted)" }}>{caption}</figcaption>}
    </figure>
  );
}
