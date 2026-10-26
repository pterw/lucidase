import React, { useState } from "react";
export function Term({ children, definition }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline" }}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} onBlur={() => setOpen(false)} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        style={{ font: "inherit", color: "inherit", background: "none", border: 0, padding: 0, cursor: "help", textDecoration: "underline dotted", textDecorationColor: "var(--ink-subtle)", textUnderlineOffset: 3 }}>{children}</button>
      {open && <span role="tooltip" style={{ position: "absolute", left: 0, top: "calc(100% + 6px)", zIndex: "var(--z-menu)", width: 280, padding: "10px 12px", background: "var(--ink)", color: "var(--on-ink)", font: "400 14px/1.5 var(--font-sans)", borderRadius: "var(--radius-control)", textAlign: "left" }}>{definition}</span>}
    </span>
  );
}
