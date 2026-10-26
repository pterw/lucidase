import React from "react";
export function StatusDot({ tone = "ok", size = 8, halo = false, label }) {
  const c = tone === "ok" ? "var(--ok)" : tone === "accent" ? "var(--accent)" : tone === "muted" ? "var(--ink-subtle)" : "var(--state-" + tone + ")";
  return <span role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}
    style={{ display: "inline-block", flex: "none", width: size, height: size, borderRadius: "var(--radius-dot)", background: c,
      boxShadow: halo ? "0 0 0 " + Math.round(size * 0.6) + "px color-mix(in srgb, " + c + " 22%, transparent)" : "none" }} />;
}
