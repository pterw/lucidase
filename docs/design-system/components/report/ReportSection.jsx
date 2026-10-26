import React from "react";
export function ReportSection({ title, aside, id, children, style }) {
  return (
    <section id={id} aria-labelledby={id ? id + "-h" : undefined} style={{ display: "flex", flexWrap: "wrap", columnGap: 40, rowGap: 16, paddingTop: 28, borderTop: "1px solid var(--border-default)", ...style }}>
      <div style={{ flex: "0 1 var(--margin-col)", minWidth: 180, display: "flex", flexDirection: "column", gap: 8 }}>
        <h2 id={id ? id + "-h" : undefined} style={{ margin: 0, font: "400 24px/1.2 var(--font-serif)", letterSpacing: "var(--tracking-heading)", color: "var(--text-body)", textWrap: "balance" }}>{title}</h2>
        {aside && <div style={{ font: "400 14px/1.5 var(--font-sans)", color: "var(--text-muted)", textWrap: "pretty" }}>{aside}</div>}
      </div>
      <div style={{ flex: "1 1 520px", minWidth: 0 }}>{children}</div>
    </section>
  );
}
