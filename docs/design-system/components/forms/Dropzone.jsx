import React, { useRef, useState } from "react";
import { Icon } from "../core/Icon.jsx";
export function Dropzone({ title = "Drop your raw DNA file here", description, accept = ".txt,.csv,.vcf,.tsv,.gz", onFile, disabled, children, style }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const [focus, setFocus] = useState(false);
  const pick = () => { if (!disabled && input.current) input.current.click(); };
  return (
    <div role="button" tabIndex={disabled ? -1 : 0} aria-disabled={disabled || undefined} aria-label={title}
      onClick={e => { if (e.target.closest("button,a")) return; pick(); }}
      onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } }}
      onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
      onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f && onFile) onFile(f); }}
      style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 14, padding: "28px 28px 24px", background: over ? "var(--accent-wash)" : "var(--bg-panel)", border: "1.5px dashed " + (over || focus ? "var(--accent)" : "var(--border-control)"), borderRadius: "var(--radius-panel)", cursor: disabled ? "not-allowed" : "pointer", outline: "none", transition: "background-color var(--dur-fast) ease, border-color var(--dur-fast) ease", ...style }}>
      <input ref={input} type="file" accept={accept} hidden onChange={e => { const f = e.target.files[0]; if (f && onFile) onFile(f); }} />
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}><Icon name="file-up" size={22} style={{ color: over ? "var(--accent-ink)" : "var(--ink)" }} /><span style={{ font: "700 17px var(--font-sans)", color: "var(--text-body)" }}>{title}</span></div>
      {description && <div style={{ font: "400 15px/1.55 var(--font-sans)", color: "var(--text-muted)", maxWidth: "var(--measure-prose)", textWrap: "pretty" }}>{description}</div>}
      {children && <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>{children}</div>}
    </div>
  );
}
