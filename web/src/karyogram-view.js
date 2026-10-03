/**
 * Karyogram SVG view (contracts K-C3). Pure: returns a string, deterministic for a given layout.
 *
 * Colours come only from CSS classes, never inline fills. Every text node and attribute value goes through
 * escapeHtml. Coordinates are formatted with toFixed(1) and the element order is fixed.
 */
import { escapeHtml } from "./view-model.js";
import { DEFAULT_BIN_SIZE, binIndex } from "./core/karyogram.js";

const COLUMN_PITCH = 28;
const BIN_PITCH = 7;
const TOP_PAD = 24;
const LABEL_GAP = 14;
const BOTTOM_PAD = 10;
const CEN_TICK = 6;
const LOCUS_STEP = 10;
const R_MIN = 0.9;
const R_SPAN = 2.3;

const f = (n) => n.toFixed(1);
const esc = escapeHtml;

export function renderKaryogramSvg(layout, { stateLabels = {} } = {}) {
  const { geometry, reference, sample } = layout;
  const labelOf = (state) => stateLabels[state] ?? state;
  const binSize = sample ? sample.binSize : DEFAULT_BIN_SIZE;
  const drawDensity = Boolean(sample && sample.density === "available" && sample.bins);

  const cols = geometry.chromosomes.map((c, i) => ({
    ...c,
    x: COLUMN_PITCH / 2 + i * COLUMN_PITCH,
    nBins: Math.ceil(c.length / binSize),
    cenBin: binIndex(c.centromere[0], binSize),
    cenLast: binIndex(c.centromere[1], binSize),
  }));

  const cenY = TOP_PAD + Math.max(...cols.map((c) => c.cenBin)) * BIN_PITCH;
  const binY = (col, i) => cenY + (i - col.cenBin) * BIN_PITCH;
  const lowestY = Math.max(...cols.map((c) => binY(c, c.nBins - 1)));
  const width = cols.length * COLUMN_PITCH;
  const height = lowestY + LABEL_GAP + BOTTOM_PAD;

  let maxCount = 0;
  if (drawDensity) {
    for (const c of cols) for (const n of sample.bins[c.name]) if (n > maxCount) maxCount = n;
  }

  const parts = [];
  for (const c of cols) {
    const g = [`<g class="kary-col" data-chrom="${esc(c.name)}">`];
    for (let i = 0; i < c.nBins; i++) {
      const y = binY(c, i);
      const count = drawDensity ? sample.bins[c.name][i] : 0;
      // A centromere bin draws the tick only when it holds no markers; a bin with markers is a dot like any other.
      if (i >= c.cenBin && i <= c.cenLast && count === 0) {
        g.push(
          `<line class="kary-cen" x1="${f(c.x - CEN_TICK / 2)}" y1="${f(y)}" x2="${f(c.x + CEN_TICK / 2)}" y2="${f(y)}"/>`,
        );
        continue;
      }
      if (count > 0) {
        const r = R_MIN + R_SPAN * Math.sqrt(count / maxCount);
        g.push(`<circle class="kary-bin" cx="${f(c.x)}" cy="${f(y)}" r="${f(r)}"/>`);
      } else {
        g.push(`<circle class="kary-bin kary-bin-empty" cx="${f(c.x)}" cy="${f(y)}" r="${f(R_MIN)}"/>`);
      }
    }
    g.push(
      `<text class="kary-label" x="${f(c.x)}" y="${f(binY(c, c.nBins - 1) + LABEL_GAP)}" font-size="10" text-anchor="middle">${esc(c.name)}</text>`,
    );
    g.push("</g>");
    parts.push(g.join(""));
  }

  // Loci: group by chromosome bin, spread horizontally in 10 px steps, centred on the column.
  const colByName = Object.fromEntries(cols.map((c) => [c.name, c]));
  const groups = new Map();
  for (const l of reference.loci) {
    if (!colByName[l.chrom]) {
      throw new Error(`renderKaryogramSvg: locus ${l.rsid} is on undrawn chromosome ${l.chrom}`);
    }
    const key = `${l.chrom}:${binIndex(l.pos, binSize)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(l.rsid);
  }
  const stateCounts = new Map();
  for (const l of reference.loci) {
    const col = colByName[l.chrom];
    const idx = binIndex(l.pos, binSize);
    const peers = groups.get(`${l.chrom}:${idx}`);
    const x = col.x + (peers.indexOf(l.rsid) - (peers.length - 1) / 2) * LOCUS_STEP;
    const y = binY(col, idx);
    const state = sample ? sample.observations[l.rsid] : "reference";
    stateCounts.set(state, (stateCounts.get(state) ?? 0) + 1);
    parts.push(
      `<g class="kary-locus kary-state-${esc(state)}" data-rsid="${esc(l.rsid)}" data-state="${esc(state)}">` +
        `<title>${esc(l.gene)} ${esc(l.rsid)}: ${esc(labelOf(state))}</title>` +
        `<circle class="kary-halo" cx="${f(x)}" cy="${f(y)}" r="10"/>` +
        `<circle class="kary-core" cx="${f(x)}" cy="${f(y)}" r="5"/></g>`,
    );
  }

  const markerText = !sample
    ? "no sample"
    : sample.density === "available"
      ? `${sample.totals.placed} markers placed`
      : "density unavailable";
  const stateText = [...stateCounts].map(([s, n]) => `${labelOf(s)}: ${n}`).join("; ");
  const title = `Karyogram (${geometry.build})`;
  const desc = `${markerText}. Loci per state: ${stateText}.`;

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${f(width)}" height="${f(height)}" viewBox="0 0 ${f(width)} ${f(height)}" role="img" aria-labelledby="kary-title kary-desc">` +
    `<title id="kary-title">${esc(title)}</title><desc id="kary-desc">${esc(desc)}</desc>` +
    parts.join("") +
    "</svg>"
  );
}
