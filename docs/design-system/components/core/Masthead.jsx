import React from "react";
import { Wordmark } from "./Wordmark.jsx";
export function Masthead({ basePath = "assets/logo/", width = 640, mark = true, title, children, style }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28, padding: "8px 0 4px", ...style }}>
      {mark ? <div style={{ width: "100%", maxWidth: width }}>
        <img className="lds-wm-light" src={basePath + "lucidase-lockup-light.svg"} alt="Lucidase" style={{ width: "100%", height: "auto" }} />
        <img className="lds-wm-dark" src={basePath + "lucidase-lockup-dark.svg"} alt="Lucidase" style={{ width: "100%", height: "auto" }} />
      </div> : <div style={{ padding: "12px 0" }}><Wordmark height={56} basePath={basePath} /></div>}
      {title && <h1 style={{ margin: 0, font: "400 40px/1.1 var(--font-serif)", letterSpacing: "-0.02em", maxWidth: 620, textWrap: "balance" }}>{title}</h1>}
      {children}
    </div>
  );
}
