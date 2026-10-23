import React from "react";
export function LocalNote({ children = "Read in this browser" }) {
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 8, font: "400 13px var(--font-sans)", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
    <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: "var(--radius-dot)", background: "var(--ok)" }} />{children}</span>;
}
