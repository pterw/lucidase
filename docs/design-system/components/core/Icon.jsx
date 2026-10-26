import React from "react";
const CDN = "https://unpkg.com/lucide-static@0.469.0/icons/";
export function Icon({ name, size = 16, label, style, ...rest }) {
  const url = "url(" + CDN + name + ".svg)";
  return (
    <span role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}
      style={{ display: "inline-block", flex: "none", width: size, height: size, backgroundColor: "currentColor",
        WebkitMaskImage: url, maskImage: url, WebkitMaskSize: "contain", maskSize: "contain",
        WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", WebkitMaskPosition: "center", maskPosition: "center", ...style }} {...rest} />
  );
}
