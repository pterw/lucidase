import React from "react";
export function Wordmark({ height = 28, theme, basePath = "assets/logo/", style }) {
  const img = (t, cls) => <img className={cls} src={basePath + "lucidase-wordmark-" + t + ".svg"} alt={cls === "lds-wm-dark" && !theme ? "" : "Lucidase"} aria-hidden={cls === "lds-wm-dark" && !theme ? true : undefined} height={height} style={{ height: height, width: "auto", ...style }} />;
  if (theme) return <span style={{ display: "inline-flex" }}>{img(theme === "dark" ? "dark" : "light")}</span>;
  return <span style={{ display: "inline-flex" }}>{img("light", "lds-wm-light")}{img("dark", "lds-wm-dark")}</span>;
}
