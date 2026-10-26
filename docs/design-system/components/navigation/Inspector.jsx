import React, { useEffect, useRef } from "react";
import { IconButton } from "../core/IconButton.jsx";
export function Inspector({ open, onClose, title, subtitle, meta, children, footer, style }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const esc = e => { if (e.key === "Escape" && onClose) onClose(); };
    document.addEventListener("keydown", esc);
    if (ref.current) ref.current.focus();
    return () => document.removeEventListener("keydown", esc);
  }, [open]);
  if (!open) return null;
  return (
    <aside ref={ref} tabIndex={-1} aria-label={typeof title === "string" ? title + " details" : "Details"}
      style={{ position: "sticky", top: 16, maxHeight: "calc(100vh - 32px)", display: "flex", flexDirection: "column", background: "var(--bg-panel)", border: "1px solid var(--border-default)", outline: "none", ...style }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, padding: "18px 20px 14px", borderBottom: "1px solid var(--border-default)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <div style={{ font: "400 26px/1.15 var(--font-serif)", letterSpacing: "var(--tracking-heading)", color: "var(--text-body)" }}>{title}</div>
          {subtitle && <div style={{ font: "400 13px var(--font-mono)", color: "var(--text-muted)" }}>{subtitle}</div>}
          {meta && <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 2 }}>{meta}</div>}
        </div>
        <IconButton icon="x" label="Close details" onClick={onClose} />
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 20px 20px" }}>{children}</div>
      {footer && <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "12px 20px", borderTop: "1px solid var(--border-default)" }}>{footer}</div>}
    </aside>
  );
}
export function InspectorSection({ title, children }) {
  return (
    <section style={{ padding: "16px 0", borderBottom: "1px solid var(--border-default)" }}>
      {title && <h3 style={{ margin: "0 0 8px", font: "700 15px/1.3 var(--font-sans)", color: "var(--text-body)" }}>{title}</h3>}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, font: "400 16px/1.55 var(--font-serif)", color: "var(--text-body)" }}>{children}</div>
    </section>
  );
}
