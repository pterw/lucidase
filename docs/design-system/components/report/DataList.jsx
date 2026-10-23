import React from "react";
import { NotAvailable } from "../feedback/NotAvailable.jsx";
export function DataList({ items, columns = 2, style }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "repeat(" + columns + ", minmax(0,1fr))", margin: 0, borderTop: "1px solid var(--border-default)", ...style }}>
      {items.map((it, i) => (
        <div key={i} style={{ padding: "10px 0", paddingRight: 16, borderBottom: "1px solid var(--border-default)", minWidth: 0 }}>
          <dt style={{ font: "400 12px var(--font-sans)", color: "var(--text-muted)" }}>{it.term}</dt>
          <dd style={{ margin: "2px 0 0", font: "700 14px/1.4 " + (it.mono === false ? "var(--font-sans)" : "var(--font-mono)"), color: it.tone ? "var(--state-" + it.tone + "-ink)" : "var(--text-body)", overflowWrap: "anywhere" }}>
            {it.value === null || it.value === undefined ? <NotAvailable reason={it.reason} /> : it.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
