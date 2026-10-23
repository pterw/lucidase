import React, { useState } from "react";
export function DataTable({ columns, rows, rowKey = "id", onRowClick, selectedKey, empty = "No findings match this filter.", caption, maxHeight, style }) {
  const [hover, setHover] = useState(null);
  return (
    <div style={{ overflow: "auto", maxHeight: maxHeight, ...style }}>
      <table style={{ width: "100%", borderCollapse: "collapse", font: "400 13px/1.45 var(--font-sans)", color: "var(--text-body)" }}>
        {caption && <caption style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>{caption}</caption>}
        <thead>
          <tr>{columns.map(c => <th key={c.key} scope="col" style={{ position: "sticky", top: 0, zIndex: 1, textAlign: c.align || "left", padding: "10px 16px", background: "var(--bg-sunk)", borderBottom: "1px solid var(--border-strong)", font: "700 13px var(--font-condensed)", letterSpacing: "var(--tracking-label)", color: "var(--text-muted)", whiteSpace: "nowrap", width: c.width }}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={columns.length} style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-muted)", font: "italic 400 15px var(--font-serif)" }}>{empty}</td></tr>}
          {rows.map((r, i) => {
            const k = r[rowKey] != null ? r[rowKey] : i; const sel = selectedKey === k;
            return (
              <tr key={k} tabIndex={onRowClick ? 0 : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined}
                onKeyDown={onRowClick ? e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(r); } } : undefined}
                onMouseEnter={() => setHover(k)} onMouseLeave={() => setHover(null)}
                style={{ cursor: onRowClick ? "pointer" : "default", background: sel ? "var(--accent-wash)" : hover === k ? "var(--bg-hover)" : "transparent", transition: "background-color var(--dur-instant) ease" }}>
                {columns.map(c => <td key={c.key} style={{ padding: "11px 16px", borderBottom: "1px solid var(--border-default)", textAlign: c.align || "left", verticalAlign: "top", font: c.mono ? "400 13px var(--font-mono)" : undefined, whiteSpace: c.wrap ? "normal" : "nowrap", maxWidth: c.maxWidth }}>{c.render ? c.render(r) : r[c.key]}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
