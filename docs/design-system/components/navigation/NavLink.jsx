import React from "react";
import { useHover } from "../core/hooks.js";
export function NavLink({ active, href, onClick, children }) {
  const [h, hp] = useHover();
  return <a href={href || "#"} aria-current={active ? "page" : undefined} onClick={onClick} {...hp}
    style={{ display: "flex", alignItems: "center", minHeight: 44, padding: "0 10px", font: "700 15px var(--font-sans)", textDecoration: "none",
      color: active || h ? "var(--text-body)" : "var(--text-muted)", boxShadow: active ? "inset 0 -2px 0 var(--accent)" : "none" }}>{children}</a>;
}
