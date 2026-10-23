import React, { useState } from "react";
import { Icon } from "../core/Icon.jsx";
export function SearchInput({ value, onChange, placeholder = "Search gene, rsID or drug", label = "Search findings", width = 260, style }) {
  const [focus, setFocus] = useState(false);
  return (
    <label style={{ position: "relative", display: "inline-flex", alignItems: "center", width: width, ...style }}>
      <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>{label}</span>
      <Icon name="search" size={15} style={{ position: "absolute", left: 10, color: "var(--text-subtle)" }} />
      <input type="search" value={value} placeholder={placeholder} onChange={e => onChange && onChange(e.target.value)}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={{ width: "100%", height: 36, padding: "0 10px 0 32px", font: "400 14px var(--font-sans)", color: "var(--text-body)",
          background: "var(--bg-panel)", border: "1px solid " + (focus ? "var(--accent)" : "var(--border-control)"), borderRadius: "var(--radius-control)",
          outline: "none", boxShadow: focus ? "0 0 0 3px var(--accent-wash)" : "none", boxSizing: "border-box" }} />
    </label>
  );
}
