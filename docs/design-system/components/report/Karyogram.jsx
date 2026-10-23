import React from "react";
import { stateMeta } from "../core/hooks.js";
const CHR = [["1",248.96,123.4],["2",242.19,93.9],["3",198.3,90.9],["4",190.21,50],["5",181.54,48.8],["6",170.81,59.8],["7",159.35,60.1],["8",145.14,45.2],["9",138.39,43],["10",133.8,39.8],["11",135.09,53.4],["12",133.28,35.5],["13",114.36,17.7],["14",107.04,17.2],["15",101.99,19],["16",90.34,36.8],["17",83.26,25.1],["18",80.37,18.5],["19",58.62,26.2],["20",64.44,28.1],["21",46.71,12],["22",50.82,15],["X",156.04,60.6],["Y",57.23,10.4]];
function seeded(i) { const x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); }
export function Karyogram({ loci = [], density = false, selected, onSelect, height, title = "Where the genes this report checks sit on your chromosomes" }) {
  const W = 760, top = 18, scale = 1.25, gap = W / 25, H = height || top + 249 * scale + 30;
  return (
    <svg viewBox={"0 0 " + W + " " + H} role="img" aria-label={title} style={{ display: "block", width: "100%", height: "auto" }}>
      <title>{title}</title>
      {CHR.map(([c, len, cen], ci) => {
        const x = gap * (ci + 1), bins = Math.ceil(len / 4), dots = [];
        for (let b = 0; b < bins; b++) {
          const y = top + (b * 4 + 2) * scale;
          if (Math.abs(b * 4 + 2 - cen) < 2) { dots.push(<line key={"c" + b} x1={x - 4} x2={x + 4} y1={y} y2={y} stroke="var(--ink-subtle)" strokeWidth="1.5" />); continue; }
          const r = density ? 1.5 + seeded(ci * 100 + b) * 1.5 : 1.6;
          dots.push(<circle key={b} cx={x} cy={y} r={r} fill="var(--dot)" />);
        }
        return <g key={c}>{dots}<text x={x} y={top + len * scale + 15} textAnchor="middle" style={{ font: "400 11px var(--font-mono)", fill: "var(--ink-muted)" }}>{c}</text></g>;
      })}
      {loci.map((l, i) => {
        const ci = CHR.findIndex(r => r[0] === l.chrom); if (ci < 0) return null;
        const x = gap * (ci + 1) + (l.offset || 0), y = top + l.pos * scale;
        const m = stateMeta[l.state]; const tone = m ? m.tone : null;
        const fill = l.state === "reference" || !tone ? "var(--ink-subtle)" : "var(--state-" + tone + ")";
        const hollow = tone === "not-observed" || tone === "array-gap"; const sel = selected === l.id;
        return (
          <g key={l.id || i} tabIndex={onSelect ? 0 : undefined} role={onSelect ? "button" : undefined} aria-label={l.label + (m ? ": " + m.label : "")}
            onClick={onSelect ? () => onSelect(l.id) : undefined} onKeyDown={onSelect ? e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(l.id); } } : undefined}
            style={{ cursor: onSelect ? "pointer" : "default", outline: "none" }}>
            <circle cx={x} cy={y} r={sel ? 11 : 8.5} fill={fill} fillOpacity={sel ? 0.3 : 0.2} />
            <circle cx={x} cy={y} r="4.25" fill={hollow ? "var(--bg-canvas)" : fill} stroke={fill} strokeWidth={hollow ? 1.75 : 1} strokeDasharray={tone === "array-gap" ? "2 1.6" : undefined} />
            <title>{l.label}</title>
          </g>
        );
      })}
    </svg>
  );
}
