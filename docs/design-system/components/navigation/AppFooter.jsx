import React from "react";
import { ThemeToggle } from "../forms/ThemeToggle.jsx";
export function AppFooter({ left = "Lucidase · not a diagnostic test, not medical advice", right = "Your file is read in this browser and never uploaded.", theme = true, style }) {
  return (
    <footer style={{ borderTop: "1px solid var(--border-default)", font: "400 13px var(--font-sans)", color: "var(--text-muted)", ...style }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "8px 24px", maxWidth: "var(--layout-max)", margin: "0 auto", padding: "16px var(--layout-gutter)" }}>
        <span>{left}</span><span style={{ flex: "1 1 auto" }}>{right}</span>{theme && <ThemeToggle />}
      </div>
    </footer>
  );
}
