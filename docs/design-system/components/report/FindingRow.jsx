import React from "react";
import { StateMark } from "../core/StateMark.jsx";
import { Icon } from "../core/Icon.jsx";
import { useHover } from "../core/hooks.js";
export function FindingRow({ gene, topic, statement, state, limitation, technical, onOpen, selected }) {
  const [h, hp] = useHover();
  return (
    <article {...hp} style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr) auto", columnGap: 14, rowGap: 6, padding: "16px 12px 16px 8px", margin: "0 -12px 0 -8px", borderBottom: "1px solid var(--border-default)", background: selected ? "var(--accent-wash)" : h ? "var(--bg-hover)" : "transparent", transition: "background-color var(--dur-instant) ease" }}>
      <div style={{ paddingTop: 3 }}><StateMark state={state} size={16} /></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 10 }}>
          <h3 style={{ margin: 0, font: "700 16px/1.35 var(--font-sans)", color: "var(--text-body)" }}>{topic}</h3>
          <span style={{ font: "400 13px var(--font-mono)", color: "var(--text-muted)" }}>{gene}</span>
        </div>
        <p style={{ margin: 0, font: "400 16px/1.55 var(--font-serif)", color: "var(--text-body)", maxWidth: "var(--measure-prose)", textWrap: "pretty" }}>{statement}</p>
        {limitation && <p style={{ margin: 0, display: "flex", gap: 8, font: "400 14px/1.5 var(--font-sans)", color: "var(--notice-ink)", maxWidth: "var(--measure-prose)" }}><Icon name="info" size={15} style={{ marginTop: 2 }} /><span><b>What this can’t tell you:</b> {limitation}</span></p>}
        {technical && <div style={{ font: "400 13px var(--font-mono)", color: "var(--text-muted)" }}>{technical}</div>}
      </div>
      {onOpen && <button type="button" onClick={onOpen} aria-label={"Details for " + topic} style={{ alignSelf: "start", display: "inline-flex", alignItems: "center", gap: 4, height: 32, padding: "0 8px", border: 0, background: "transparent", cursor: "pointer", font: "700 14px var(--font-sans)", color: "var(--text-link)" }}>Details<Icon name="chevron-right" size={15} /></button>}
    </article>
  );
}
