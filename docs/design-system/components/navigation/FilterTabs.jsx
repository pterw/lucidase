import React from "react";
export function FilterTabs({ tabs, value, onChange, label = "Result sets", style }) {
  return (
    <div role="tablist" aria-label={label} style={{ display: "flex", gap: 0, overflowX: "auto", borderBottom: "1px solid var(--border-default)", ...style }}>
      {tabs.map(t => {
        const on = t.id === value;
        return <button key={t.id} role="tab" type="button" aria-selected={on} onClick={() => onChange && onChange(t.id)}
          style={{ display: "inline-flex", alignItems: "center", gap: 8, height: 40, padding: "0 14px", border: 0, background: "transparent", cursor: "pointer", whiteSpace: "nowrap",
            font: "700 14px var(--font-sans)", color: on ? "var(--text-body)" : "var(--text-muted)", boxShadow: on ? "inset 0 -2px 0 var(--ink)" : "none", marginBottom: -1 }}>
          {t.label}{t.count != null && <span style={{ font: "400 12px var(--font-mono)", color: "var(--text-muted)" }}>{t.count}</span>}
        </button>;
      })}
    </div>
  );
}
