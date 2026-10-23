import React, { useEffect, useState } from "react";
import { Icon } from "../core/Icon.jsx";
import { readThemePref, applyThemePref, resolveTheme } from "../core/hooks.js";
export function ThemeToggle({ style }) {
  const [pref, setPref] = useState(readThemePref);
  const [, tick] = useState(0);
  useEffect(() => {
    applyThemePref(pref);
    if (pref !== "system" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)"); const on = () => { applyThemePref("system"); tick(n => n + 1); };
    mq.addEventListener ? mq.addEventListener("change", on) : mq.addListener(on);
    return () => { mq.removeEventListener ? mq.removeEventListener("change", on) : mq.removeListener(on); };
  }, [pref]);
  const now = resolveTheme(pref), next = now === "dark" ? "light" : "dark";
  const link = { display: "inline-flex", alignItems: "center", gap: 6, minHeight: 32, padding: 0, border: 0, background: "none", cursor: "pointer", font: "400 13px var(--font-sans)", color: "var(--text-muted)", textDecoration: "underline", textUnderlineOffset: 3, textDecorationColor: "var(--border-strong)" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 14, ...style }}>
      <button type="button" style={link} onClick={() => setPref(next)}><Icon name={next === "dark" ? "moon" : "sun"} size={14} />{next === "dark" ? "Dark theme" : "Light theme"}</button>
      {pref !== "system" && <button type="button" style={link} onClick={() => setPref("system")}>Use device setting</button>}
    </span>
  );
}
