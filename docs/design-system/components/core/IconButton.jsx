import React from "react";
import { useHover } from "./hooks.js";
import { Icon } from "./Icon.jsx";
export function IconButton({ icon, label, size = 36, variant = "ghost", style, ...rest }) {
  const [hover, hp] = useHover();
  const border = variant === "secondary" ? "1px solid " + (hover ? "var(--ink-muted)" : "var(--border-control)") : "1px solid transparent";
  return (
    <button type="button" aria-label={label} title={label} {...hp} {...rest}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: size, height: size, padding: 0,
        background: hover ? "var(--bg-hover)" : (variant === "secondary" ? "var(--bg-panel)" : "transparent"), color: "var(--text-body)",
        border, borderRadius: "var(--radius-control)", cursor: "pointer", transition: "background-color var(--dur-fast) ease", ...style }}>
      <Icon name={icon} size={Math.round(size * 0.45)} />
    </button>
  );
}
