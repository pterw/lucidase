import React from "react";
export function SegmentedControl({ options, value, onChange, label, size = "md", style }) {
  const h = size === "sm" ? 30 : 36;
  return (
    <div role="group" aria-label={label} style={{ display: "grid", gridTemplateColumns: "repeat(" + options.length + ", minmax(0,1fr))", border: "1px solid var(--border-control)", borderRadius: "var(--radius-control)", overflow: "hidden", ...style }}>
      {options.map((o, i) => {
        const id = typeof o === "string" ? o : o.value; const text = typeof o === "string" ? o : o.label; const on = id === value;
        return <button key={id} type="button" aria-pressed={on} onClick={() => onChange && onChange(id)}
          style={{ height: h, padding: "0 10px", border: 0, borderLeft: i ? "1px solid var(--border-control)" : 0, cursor: "pointer",
            font: "700 13px var(--font-sans)", background: on ? "var(--ink)" : "var(--bg-panel)", color: on ? "var(--paper)" : "var(--text-body)",
            transition: "background-color var(--dur-fast) ease" }}>{text}</button>;
      })}
    </div>
  );
}
