/**
 * Lucidase karyogram page (contracts K-C4). Owns the DOM of karyogram.html.
 *
 * The page opens on the reference-only karyogram of the knowledge-base loci. A file (or the bundled synthetic
 * sample) goes to the worker's "karyogram" action, which returns the layout; the page renders it with the pure view.
 * Every failure shows #karyogram-error and no result. Everything stays in the browser: the only requests are
 * same-origin (modules, the KB, the bundled sample).
 */

import { loadKnowledgeBase } from "./kb-loader.js";
import { layoutKaryogram, rollUpGeneResult } from "./core/karyogram.js";
import { renderKaryogramSvg } from "./karyogram-view.js";
import { RESULT_WORDS, escapeHtml, karyogramStateLabels } from "./view-model.js";
import { initTheme } from "./theme.js";
import { initPagesMenu } from "./pages-menu.js";

const SAMPLE_URL = "./demo-data/sample-karyogram-23andme.txt";
const SAMPLE_NAME = "sample-karyogram-23andme.txt";
const WORKER_TIMEOUT_MS = 30000;
const KARYOGRAM_BIN_SIZE = 4_000_000;
const LEGEND_ORDER = [
  "reference",
  "supported_and_observed",
  "supported_not_observed",
  "not_tested_by_array",
  "insufficient_evidence",
];

const labels = karyogramStateLabels();
// source: what the map shows now ({ name, isSample }), or null for the reference view; pending: the job in flight.
// isSample is set only by the built-in sample button, so a user's file that happens to share its name is never
// called a made-up example.
const view = { kb: null, layout: null, worker: null, watchdog: null, source: null, pending: null };

const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("en-US");

/** "reference-only" | "loading" | "result" | "error": read by tests and by the design handoff. */
function setViewState(name) {
  $("karyogram-main").setAttribute("data-karyogram-state", name);
}

function setInputsDisabled(disabled) {
  $("karyogram-file-input").disabled = disabled;
  $("btn-karyogram-browse").disabled = disabled;
  $("btn-load-karyogram-sample").disabled = disabled;
  const btnExport = $("btn-karyogram-export");
  if (btnExport) btnExport.disabled = disabled;
}

function updateProgress(percent, message) {
  // The bar grows by transform only (the design system's motion rule).
  $("karyogram-progress-bar").style.transform = `scaleX(${Math.min(100, Math.max(0, percent)) / 100})`;
  $("karyogram-progress-pct").textContent = `${percent}%`;
  $("karyogram-progress-msg").textContent = message;
}

function hideTotals() {
  $("karyogram-totals").classList.add("hidden");
  $("karyogram-density-notice").classList.add("hidden");
}

/** The state of one locus; an unknown state is a bug upstream, so it throws instead of rendering NaN or a raw key. */
function stateOf(layout, rsid) {
  const state = layout.sample ? layout.sample.observations[rsid] : "reference";
  if (!Object.hasOwn(labels, state) || !LEGEND_ORDER.includes(state)) {
    throw new Error(`Unknown karyogram state "${state}" for ${rsid}.`);
  }
  return state;
}

/**
 * Draws the key under the figure. With no file it is one row, the reference state ("Genes this report checks")
 * with the count of all genes; with a file it is four rows, one per result, each with its count and one-line help.
 * @param {object} layout The karyogram layout; `layout.sample` is absent until a file is read.
 */
function renderLegend(layout) {
  const counts = Object.fromEntries(LEGEND_ORDER.map((s) => [s, 0]));
  for (const l of layout.reference.loci) counts[stateOf(layout, l.rsid)] += 1;
  // Without a file every gene is "reference": one row, not four rows of zero. With a file the four results
  // are listed and "reference" has no gene left.
  const shown = LEGEND_ORDER.filter((s) => (layout.sample ? s !== "reference" : s === "reference"));
  // The design system's KaryogramLegend: mark, plain word, count, then the word's one-line help under it.
  $("karyogram-legend").innerHTML = shown.map((s) => {
    const help = Object.hasOwn(RESULT_WORDS, s) ? RESULT_WORDS[s].help : null;
    return (
      `<li class="flex flex-wrap items-center gap-x-3 py-2 border-b border-line" data-legend-state="${escapeHtml(s)}">` +
      `<span class="kary-swatch kary-state-${escapeHtml(s)}" aria-hidden="true"></span>` +
      `<span class="flex-1" data-legend-label>${escapeHtml(labels[s])}</span>` +
      `<span class="lds-data font-bold" data-legend-count="${escapeHtml(s)}">${counts[s]}</span>` +
      (help === null ? "" : `<span class="lds-meta basis-full pl-6" data-legend-help>${escapeHtml(help)}</span>`) +
      `</li>`
    );
  }).join("");
}

function renderTotals(layout) {
  const sample = layout.sample;
  if (!sample) {
    hideTotals();
    return;
  }
  const t = sample.totals;
  const unplaced = Object.entries(t.unplaced);
  const values = {
    rows: fmt(t.rows),
    placed: fmt(t.placed),
    mt: fmt(t.mt),
    unplaced: unplaced.length === 0 ? "None" : unplaced.map(([name, n]) => `${name}: ${fmt(n)}`).join(", "),
    outOfBounds: fmt(t.outOfBounds),
    notPlacedBuildUnknown: fmt(t.notPlacedBuildUnknown),
    density: sample.density === "available" ? "Yes" : "No",
  };
  for (const [name, text] of Object.entries(values)) {
    document.querySelector(`#karyogram-totals [data-total="${name}"]`).textContent = text;
  }
  $("karyogram-density-notice").classList.toggle("hidden", sample.density === "available");
  $("karyogram-totals").classList.remove("hidden");
}

/** The KB's plain-words name for a gene's topic; "Not available" when the KB has none (the loader rejects a blank topic). */
function topicOf(gene) {
  const entry = view.kb.genes[gene];
  return entry && typeof entry.topic === "string" && entry.topic !== "" ? entry.topic : "Not available";
}

/** The result cell: the swatch and the plain word with a file; the muted "No file yet" while there is no result. */
function resultCell(layout, result) {
  if (!layout.sample || result.state === "reference") return `<span class="lds-na-text">No file yet</span>`;
  return (
    `<span class="flex items-center gap-2"><span class="kary-swatch kary-state-${escapeHtml(result.state)}" aria-hidden="true"></span>` +
    `${escapeHtml(result.label)}</span>`
  );
}

function renderLoci(layout) {
  const genes = [];
  const seen = new Set();
  for (const l of layout.reference.loci) {
    if (!seen.has(l.gene)) {
      seen.add(l.gene);
      genes.push({
        gene: l.gene,
        chrom: l.chrom,
        loci: layout.reference.loci.filter((x) => x.gene === l.gene),
      });
    }
  }

  $("karyogram-loci-body").innerHTML = genes
    .map((g) => {
      const result = rollUpGeneResult(
        g.loci,
        layout.sample ? layout.sample.observations : null,
      );
      return (
        `<tr data-gene="${escapeHtml(g.gene)}" data-rsid="${escapeHtml(g.loci[0].rsid)}" data-state="${escapeHtml(result.state)}"${result.isPartial ? ` data-partial="true"` : ""}>` +
        `<td class="font-bold">${escapeHtml(topicOf(g.gene))}</td><td class="lds-data">${escapeHtml(g.gene)}</td>` +
        `<td class="lds-data">${escapeHtml(g.chrom)}</td>` +
        `<td>${resultCell(layout, result)}</td></tr>`
      );
    })
    .join("");
}

/** One line under the figure: what it is drawn from, in the design system's wording. */
function renderCaption(layout) {
  const { build } = layout.geometry;
  const source = view.source;
  let text;
  if (!source || !layout.sample) {
    text = `No file yet: the chromosomes are drawn from the ${build} reference.`;
  } else if (layout.sample.density === "unavailable") {
    text = `${source.name} · no genome version in the file, so the chromosomes are drawn from the ${build} reference.`;
  } else {
    text = `${source.name} · ${source.isSample ? "made-up example · " : ""}drawn on ${build} chromosome lengths.`;
  }
  $("karyogram-caption").textContent = text;
}

function renderProvenance(layout) {
  const { build } = layout.geometry;
  const assembly = view.kb.assemblies[build];
  const tables = assembly.sources.map((s) => `${s.table} retrieved ${s.retrieved}`).join("; ");
  const unknown = layout.sample && layout.sample.density === "unavailable";
  const shapes = !layout.sample
    ? `Chromosome shapes: ${build}.`
    : unknown
      ? `Chromosome shapes: ${build} reference, used because your file doesn't say which genome version it was made with.`
      : `Chromosome shapes: ${build}, matching your file.`;
  $("karyogram-provenance").textContent =
    `${shapes} Source: UCSC ${assembly.ucsc} tables ${tables}. ` +
    `Knowledge base release ${view.kb.manifest.release}.`;
}

/** The file buttons while the map is the reference; "Clear the file" while a file is on it. */
function syncFileControls() {
  const hasFile = view.source !== null;
  $("btn-karyogram-browse").classList.toggle("hidden", hasFile);
  $("karyogram-sample-group").classList.toggle("hidden", hasFile);
  $("btn-karyogram-clear").classList.toggle("hidden", !hasFile);
}

/** Draws a layout everywhere on the page: figure, key, totals, genes table, provenance and caption. */
function render(layout) {
  view.layout = layout;
  $("karyogram-figure").innerHTML = renderKaryogramSvg(layout, { stateLabels: labels });
  renderLegend(layout);
  renderTotals(layout);
  renderLoci(layout);
  renderProvenance(layout);
  renderCaption(layout);
  syncFileControls();
}

/** The one error path: every failure shows #karyogram-error, drops any result and goes back to the reference view. */
function showError(message) {
  stopWorker();
  view.source = null;
  view.pending = null;
  $("karyogram-progress").classList.add("hidden");
  $("karyogram-error-detail").textContent = String(message || "unknown error");
  $("karyogram-error").classList.remove("hidden");
  setInputsDisabled(false);
  setViewState("error");
  if (view.kb) {
    try {
      render(layoutKaryogram({ kb: view.kb, binSize: KARYOGRAM_BIN_SIZE }));
    } catch (err) {
      $("karyogram-error-detail").textContent += ` (and the reference view failed: ${(err && err.message) || err})`;
    }
  }
  hideTotals();
}

function stopWorker() {
  if (view.watchdog) clearTimeout(view.watchdog);
  view.watchdog = null;
  if (view.worker) view.worker.terminate();
  view.worker = null;
}

function armWatchdog(fail) {
  if (view.watchdog) clearTimeout(view.watchdog);
  view.watchdog = setTimeout(() => fail("The analysis worker stopped responding."), WORKER_TIMEOUT_MS);
}

// A worker whose module graph fails to load (a dropped request, a machine out of socket buffers) raises an
// error event with no message before it has answered anything. That is a transient start failure, so the page
// starts one fresh worker with the same job, like app.js; a worker that throws, or fails twice, takes the error path.
function startWorker(job, canRetry = true) {
  stopWorker();
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  view.worker = worker;
  let answered = false;
  const fail = (message) => {
    if (view.worker === worker) showError(message);
  };
  worker.onerror = (err) => {
    if (canRetry && !answered && view.worker === worker && !(err && err.message)) {
      try {
        startWorker(job, false).postMessage(job);
        return;
      } catch (retryErr) {
        showError((retryErr && retryErr.message) || "The analysis worker failed to start.");
        return;
      }
    }
    fail((err && err.message) || "The analysis worker failed to start.");
  };
  worker.onmessageerror = () => fail("The analysis worker sent a message the page could not read.");
  worker.onmessage = (e) => {
    if (view.worker !== worker) return;
    answered = true;
    const data = e.data;
    if (data.type === "progress") {
      armWatchdog(fail);
      updateProgress(data.percent, data.status);
    } else if (data.type === "karyogram") {
      stopWorker();
      try {
        view.source = view.pending;
        render(data.layout);
        $("karyogram-progress").classList.add("hidden");
        setInputsDisabled(false);
        setViewState("result");
        // The button that started the load is hidden now; keep the keyboard on the page's one control.
        $("btn-karyogram-clear").focus();
      } catch (err) {
        showError((err && err.message) || err);
      }
    } else if (data.type === "error") {
      fail(data.message);
    }
  };
  armWatchdog(fail);
  return worker;
}

/** Starts the analysis of one file's text; isSample marks the built-in example so its caption can say so. */
function processText(text, fileName, isSample = false) {
  view.pending = { name: fileName, isSample };
  $("karyogram-error").classList.add("hidden");
  setInputsDisabled(true);
  setViewState("loading");
  $("karyogram-progress").classList.remove("hidden");
  const job = { action: "karyogram", text, fileName };
  startWorker(job).postMessage(job);
}

function handleFileSelected(file) {
  $("karyogram-error").classList.add("hidden");
  setViewState("loading");
  $("karyogram-progress").classList.remove("hidden");
  updateProgress(5, `Reading ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)...`);
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      processText(e.target.result, file.name);
    } catch (err) {
      showError((err && err.message) || err);
    }
  };
  reader.onerror = () => showError("Failed to read file from disk.");
  reader.readAsText(file);
}

/**
 * The bundled sample's text, or a rejection once the worker's time budget runs out: a request that never answers
 * must not leave the page loading. A response that arrives after the timeout is dropped, because the race has settled.
 */
function fetchSampleText() {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("The example file did not load in time.")), WORKER_TIMEOUT_MS);
  });
  const load = fetch(SAMPLE_URL).then((resp) => {
    if (!resp.ok) throw new Error("Could not load the example file.");
    return resp.text();
  });
  return Promise.race([load, timeout]).finally(() => clearTimeout(timer));
}

/** Loads the built-in made-up example through the same path as a chosen file, flagged as the example. */
async function loadSample() {
  try {
    $("karyogram-error").classList.add("hidden");
    // Disabled for the fetch too, so a second click or a file cannot race this load; showError frees them.
    setInputsDisabled(true);
    setViewState("loading");
    $("karyogram-progress").classList.remove("hidden");
    updateProgress(10, "Loading the example file...");
    processText(await fetchSampleText(), SAMPLE_NAME, true);
  } catch (err) {
    showError((err && err.message) || err);
  }
}

/** Back to the reference view: nothing of the file stays on the page; focus goes to "Choose your DNA file". */
function clearFile() {
  stopWorker();
  view.source = null;
  view.pending = null;
  render(layoutKaryogram({ kb: view.kb, binSize: KARYOGRAM_BIN_SIZE }));
  setViewState("reference-only");
  setInputsDisabled(false);
  $("btn-karyogram-browse").focus();
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function exportKaryogramJpeg() {
  const figureSvg = document.querySelector("#karyogram-figure svg");
  if (!figureSvg) return null;

  const computed = getComputedStyle(document.documentElement);
  const bodyComputed = getComputedStyle(document.body);
  const bgCanvas = bodyComputed.backgroundColor || computed.getPropertyValue("--bg-canvas").trim() || "#0B1117";
  const ink = computed.getPropertyValue("--ink").trim() || "#EDF2F5";
  const inkMuted = computed.getPropertyValue("--ink-muted").trim() || "#97A6B2";
  const inkSubtle = computed.getPropertyValue("--ink-subtle").trim() || "#7F8D99";
  const stateObserved = computed.getPropertyValue("--state-observed").trim() || "#62E4F1";
  const stateNotObserved = computed.getPropertyValue("--state-not-observed").trim() || "#5FCB92";
  const stateArrayGap = computed.getPropertyValue("--state-array-gap").trim() || "#E9B65A";
  const stateOutside = computed.getPropertyValue("--state-outside").trim() || "#6E7D89";
  const stateInsufficient = computed.getPropertyValue("--state-insufficient").trim() || "#F2798F";

  const svgClone = figureSvg.cloneNode(true);
  const styleEl = document.createElementNS("http://www.w3.org/2000/svg", "style");
  styleEl.textContent = `
    .kary-bin { fill: ${ink}; fill-opacity: 0.8; }
    .kary-bin-empty { fill: ${inkSubtle}; fill-opacity: 0.7; }
    .kary-cen { stroke: ${inkSubtle}; stroke-width: 1.75; }
    .kary-label { fill: ${inkMuted}; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; font-size: 11px; text-anchor: middle; }

    .kary-state-supported_and_observed .kary-halo { fill: ${stateObserved}; fill-opacity: 0.15; }
    .kary-state-supported_and_observed .kary-core { fill: ${stateObserved}; stroke: ${stateObserved}; stroke-width: 1; }

    .kary-state-supported_not_observed .kary-halo { fill: ${stateNotObserved}; fill-opacity: 0.15; }
    .kary-state-supported_not_observed .kary-core { fill: ${bgCanvas}; stroke: ${stateNotObserved}; stroke-width: 1.75; }

    .kary-state-not_tested_by_array .kary-halo { fill: ${stateArrayGap}; fill-opacity: 0.15; }
    .kary-state-not_tested_by_array .kary-core { fill: ${bgCanvas}; stroke: ${stateArrayGap}; stroke-width: 1.75; stroke-dasharray: 2 1.6; }

    .kary-state-outside_coverage .kary-halo { fill: ${stateOutside}; fill-opacity: 0.15; }
    .kary-state-outside_coverage .kary-core { fill: ${stateOutside}; stroke: ${stateOutside}; stroke-width: 1; }

    .kary-state-insufficient_evidence .kary-halo { fill: ${stateInsufficient}; fill-opacity: 0.15; }
    .kary-state-insufficient_evidence .kary-core { fill: ${stateInsufficient}; stroke: ${stateInsufficient}; stroke-width: 1; clip-path: inset(0 50% 0 0); }

    .kary-state-reference .kary-halo { fill: ${inkSubtle}; fill-opacity: 0.15; }
    .kary-state-reference .kary-core { fill: ${inkSubtle}; stroke: ${inkSubtle}; stroke-width: 1; }
  `;
  svgClone.insertBefore(styleEl, svgClone.firstChild);

  const svgWidth = parseFloat(svgClone.getAttribute("width")) || 672;
  const svgHeight = parseFloat(svgClone.getAttribute("height")) || 532;
  const padX = 48;
  const padY = 40;
  const scale = 2;

  const canvas = document.createElement("canvas");
  canvas.width = Math.round((svgWidth + padX * 2) * scale);
  canvas.height = Math.round((svgHeight + padY * 2) * scale);

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = bgCanvas;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const svgString = new XMLSerializer().serializeToString(svgClone);
  const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  const blobUrl = URL.createObjectURL(svgBlob);

  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = () => {
      ctx.drawImage(img, padX * scale, padY * scale, svgWidth * scale, svgHeight * scale);
      URL.revokeObjectURL(blobUrl);
      resolve();
    };
    img.onerror = (err) => {
      URL.revokeObjectURL(blobUrl);
      reject(err);
    };
    img.src = blobUrl;
  });

  const base = view.source
    ? `Lucidase_Chromosome_Map_${view.source.name.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_")}`
    : "Lucidase_Chromosome_Map";
  const filename = `${base}.jpg`;

  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      if (blob) {
        downloadBlob(blob, filename);
        resolve({ filename, size: blob.size });
      } else {
        resolve(null);
      }
    }, "image/jpeg", 0.95);
  });
}

async function initPage() {
  initTheme();
  initPagesMenu();
  window.__lucidaseKaryogram = {
    get layout() {
      return view.layout;
    },
    exportJpeg: exportKaryogramJpeg,
  };
  const fileInput = $("karyogram-file-input");
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFileSelected(e.target.files[0]);
    fileInput.value = "";
  });
  $("btn-karyogram-browse").addEventListener("click", () => fileInput.click());
  $("btn-load-karyogram-sample").addEventListener("click", loadSample);
  $("btn-karyogram-clear").addEventListener("click", () => {
    try {
      clearFile();
    } catch (err) {
      showError((err && err.message) || err);
    }
  });
  const btnExport = $("btn-karyogram-export");
  if (btnExport) {
    btnExport.addEventListener("click", () => {
      exportKaryogramJpeg().catch((err) => showError((err && err.message) || err));
    });
  }
  try {
    view.kb = await loadKnowledgeBase();
    render(layoutKaryogram({ kb: view.kb, binSize: KARYOGRAM_BIN_SIZE }));
    setViewState("reference-only");
  } catch (err) {
    showError((err && err.message) || err);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initPage);
} else {
  initPage();
}
