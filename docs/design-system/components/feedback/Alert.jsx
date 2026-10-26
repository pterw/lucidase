import React from "react";
import { Icon } from "../core/Icon.jsx";
const T = { danger: ["var(--danger-ink)", "var(--danger-wash)", "var(--danger-line)", "circle-alert"], notice: ["var(--notice-ink)", "var(--notice-wash)", "var(--notice-line)", "triangle-alert"], info: ["var(--accent-ink)", "var(--accent-wash)", "var(--accent-line)", "info"] };
export function Alert({ tone = "notice", title, children, detail, style }) {
  const [c, bg, ln, ic] = T[tone] || T.notice;
  return (
    <div role={tone === "danger" ? "alert" : "note"} style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr)", gap: 12, padding: "14px 16px", background: bg, border: "1px solid " + ln, borderRadius: "var(--radius-panel)", ...style }}>
      <Icon name={ic} size={18} style={{ color: c, marginTop: 1 }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        {title && <div style={{ font: "700 14px/1.4 var(--font-sans)", color: c }}>{title}</div>}
        {children && <div style={{ font: "400 15px/1.55 var(--font-serif)", color: "var(--text-body)", textWrap: "pretty" }}>{children}</div>}
        {detail && <div style={{ font: "400 12px/1.5 var(--font-mono)", color: c }}>{detail}</div>}
      </div>
    </div>
  );
}
