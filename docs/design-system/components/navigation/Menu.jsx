import React, { useEffect, useRef, useState } from "react";
import { Button } from "../core/Button.jsx";
import { Icon } from "../core/Icon.jsx";
export function Menu({ label, icon, items, variant = "secondary", size = "sm", align = "end" }) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(-1);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const off = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = e => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", off); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span ref={ref} style={{ position: "relative", display: "inline-flex" }}>
      <Button variant={variant} size={size} icon={icon} iconRight="chevron-down" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>{label}</Button>
      {open && (
        <ul role="menu" style={{ position: "absolute", top: "calc(100% + 4px)", [align === "end" ? "right" : "left"]: 0, zIndex: "var(--z-menu)", minWidth: 200, margin: 0, padding: 4, listStyle: "none", background: "var(--bg-panel)", border: "1px solid var(--border-default)", boxShadow: "var(--shadow-menu)", borderRadius: "var(--radius-control)" }}>
          {items.map((it, i) => (
            <li key={i} role="none">
              <button role="menuitem" type="button" onMouseEnter={() => setHi(i)} onMouseLeave={() => setHi(-1)} onClick={() => { setOpen(false); it.onSelect && it.onSelect(); }}
                style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "8px 10px", border: 0, background: hi === i ? "var(--bg-hover)" : "transparent", cursor: "pointer", textAlign: "left", font: "400 14px var(--font-sans)", color: "var(--text-body)", borderRadius: "var(--radius-control)" }}>
                {it.icon && <Icon name={it.icon} size={15} style={{ color: "var(--text-muted)" }} />}
                <span style={{ flex: 1 }}>{it.label}</span>
                {it.hint && <span style={{ font: "400 12px var(--font-mono)", color: "var(--text-subtle)" }}>{it.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
