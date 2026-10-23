import React from "react";
import { useHover } from "./hooks.js";
import { Icon } from "./Icon.jsx";
const SIZES = { sm: { h: 32, px: 12, fs: 14 }, md: { h: 40, px: 16, fs: 15 }, lg: { h: 48, px: 20, fs: 16 } };
export function Button({ variant = "primary", size = "md", icon, iconRight, disabled, children, style, as, href, ...rest }) {
  const [hover, hp] = useHover();
  const s = SIZES[size] || SIZES.md;
  const v = {
    primary: { background: hover ? "var(--ink-muted)" : "var(--ink)", color: "var(--on-ink)", border: "1px solid transparent" },
    secondary: { background: hover ? "var(--bg-hover)" : "transparent", color: "var(--text-body)", border: "1px solid " + (hover ? "var(--ink)" : "var(--border-control)") },
    ghost: { background: hover ? "var(--bg-hover)" : "transparent", color: "var(--text-body)", border: "1px solid transparent" },
    link: { background: "transparent", color: "var(--text-link)", border: "1px solid transparent", textDecoration: "underline", textUnderlineOffset: 3, padding: 0, height: "auto" }
  }[variant];
  const Tag = href ? "a" : (as || "button");
  return (
    <Tag href={href} type={Tag === "button" ? "button" : undefined} disabled={disabled} aria-disabled={disabled || undefined} {...hp} {...rest}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, height: s.h, padding: "0 " + s.px + "px",
        font: "700 " + s.fs + "px/1 var(--font-sans)", letterSpacing: "var(--tracking-ui)", borderRadius: "var(--radius-control)",
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.45 : 1, textDecoration: "none", whiteSpace: "nowrap",
        transition: "background-color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)", ...v, ...style }}>
      {icon && <Icon name={icon} size={s.fs + 2} />}
      {children}
      {iconRight && <Icon name={iconRight} size={s.fs + 2} />}
    </Tag>
  );
}
