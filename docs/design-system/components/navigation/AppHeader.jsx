import React, { useEffect, useRef, useState } from "react";
import { Icon } from "../core/Icon.jsx";
import { useWidth } from "../core/hooks.js";
export function AppHeader({ name = "Lucidase", homeHref = "#", nav, status, theme, onThemeChange, breakpoint = 680, style }) {
  const ref = useRef(null), btn = useRef(null);
  const w = useWidth(ref), narrow = w < breakpoint;
  const [open, setOpen] = useState(false);
  useEffect(() => { if (!narrow) setOpen(false); }, [narrow]);
  useEffect(() => {
    if (!open) return;
    const esc = e => { if (e.key === "Escape") { setOpen(false); btn.current && btn.current.focus(); } };
    document.addEventListener("keydown", esc); return () => document.removeEventListener("keydown", esc);
  }, [open]);
  return (
    <header ref={ref} style={{ borderBottom: "1px solid var(--border-default)", ...style }}>
      <a href="#main" style={{ position: "absolute", left: -9999, top: 0 }} onFocus={e => { e.currentTarget.style.left = "8px"; }} onBlur={e => { e.currentTarget.style.left = "-9999px"; }}>Skip to content</a>
      <div style={{ display: "flex", alignItems: "center", gap: narrow ? 4 : 28, minHeight: 56, maxWidth: "var(--layout-max)", margin: "0 auto", padding: "0 " + (narrow ? 12 : 24) + "px" }}>
        <a href={homeHref} style={{ font: "700 16px var(--font-sans)", letterSpacing: "-0.01em", color: "var(--text-body)", textDecoration: "none", padding: "8px 0" }}>{name}</a>
        {!narrow && nav && <nav aria-label="Main" style={{ display: "flex", alignItems: "center", gap: 2 }}>{nav}</nav>}
        <div style={{ flex: 1 }} />
        {!narrow && status}
        {narrow && nav && <button ref={btn} type="button" aria-expanded={open} aria-controls="lds-nav" onClick={() => setOpen(!open)}
          style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 40, padding: "0 10px", border: 0, background: open ? "var(--bg-hover)" : "transparent", color: "var(--text-body)", font: "700 14px var(--font-sans)", cursor: "pointer", borderRadius: "var(--radius-control)" }}>
          <Icon name={open ? "x" : "menu"} size={16} />Pages</button>}
      </div>
      {narrow && open && <nav id="lds-nav" aria-label="Main" style={{ display: "flex", flexDirection: "column", padding: "4px 12px 12px", borderTop: "1px solid var(--border-default)" }}>
        <div onClick={() => setOpen(false)} style={{ display: "flex", flexDirection: "column" }}>{nav}</div>{status && <div style={{ padding: "10px 10px 0" }}>{status}</div>}</nav>}
    </header>
  );
}
