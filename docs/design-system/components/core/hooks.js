import { useState, useEffect } from "react";
export function useHover() {
  const [h, setH] = useState(false);
  return [h, { onMouseEnter: () => setH(true), onMouseLeave: () => setH(false) }];
}
export const stateMeta = {
  supported_and_observed: { tone: "observed", label: "Found" },
  supported_not_observed: { tone: "not-observed", label: "Not found" },
  not_tested_by_array: { tone: "array-gap", label: "Not on your chip" },
  outside_coverage: { tone: "outside", label: "Not checked" },
  insufficient_evidence: { tone: "insufficient", label: "Unclear" }
};
export const categoryTone = { "Pathogenic": "pathogenic", "Risk Factor": "risk", "Carrier": "carrier", "Pharmacogenomics": "pgx", "Trait": "trait", "Not detected": "not-detected" };
export const stateHelp = {
  supported_and_observed: "Your file has the variant this check looks for.",
  supported_not_observed: "Your file was checked here and the variant was not found among the variants tested. This is not the same as 'normal'.",
  not_tested_by_array: "Your DNA chip did not read this position, or the reading failed. No result.",
  outside_coverage: "Markers in your file that Lucidase does not interpret. Counted only.",
  insufficient_evidence: "A reading exists, but the evidence or the genotype is not clear enough to report a result."
};

export function useWidth(ref) {
  const [w, setW] = useState(9999);
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(es => setW(es[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return w;
}
const THEME_KEY = "lucidase-theme";
export function readThemePref() { try { const v = localStorage.getItem(THEME_KEY); return v === "dark" || v === "light" ? v : "system"; } catch (e) { return "system"; } }
export function resolveTheme(pref) { if (pref === "light" || pref === "dark") return pref; try { return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; } catch (e) { return "light"; } }
export function applyThemePref(pref) {
  try { if (pref === "system") localStorage.removeItem(THEME_KEY); else localStorage.setItem(THEME_KEY, pref); } catch (e) {}
  document.documentElement.setAttribute("data-theme", resolveTheme(pref));
}
