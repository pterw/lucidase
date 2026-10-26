import React from "react";
import { StateMark } from "../core/StateMark.jsx";
import { stateHelp } from "../core/hooks.js";
export function KaryogramLegend({ items, help = true, style }) {
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", ...style }}>
      {items.map(it => (
        <li key={it.state} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", columnGap: 12, padding: "10px 0", borderBottom: "1px solid var(--border-default)" }}>
          <StateMark state={it.state} withLabel label={it.label} />
          <span style={{ font: "700 15px var(--font-mono)" }}>{it.count}</span>
          {help && stateHelp[it.state] && <span style={{ gridColumn: "1 / -1", paddingLeft: 22, font: "400 13px/1.45 var(--font-sans)", color: "var(--text-muted)" }}>{stateHelp[it.state]}</span>}
        </li>
      ))}
    </ul>
  );
}
