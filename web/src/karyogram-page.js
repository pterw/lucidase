/**
 * Lucidase karyogram page (contracts K-C4). Owns the DOM of karyogram.html.
 *
 * The page opens on the reference-only karyogram of the knowledge-base loci. A file (or the bundled synthetic
 * sample) goes to the worker's "karyogram" action, which returns the layout; the page renders it with the pure view.
 * Every failure shows #karyogram-error and no result. Everything stays in the browser: the only requests are
 * same-origin (modules, the KB, the bundled sample).
 */

import { loadKnowledgeBase } from "./kb-loader.js";
import { layoutKaryogram } from "./core/karyogram.js";
import { renderKaryogramSvg } from "./karyogram-view.js";
import { escapeHtml, karyogramStateLabels } from "./view-model.js";
import { initTheme } from "./theme.js";

const SAMPLE_URL = "./demo-data/sample-karyogram-23andme.txt";
const SAMPLE_NAME = "sample-karyogram-23andme.txt";
const WORKER_TIMEOUT_MS = 30000;
const LEGEND_ORDER = [
  "reference",
  "supported_and_observed",
  "supported_not_observed",
  "not_tested_by_array",
  "insufficient_evidence",
];

const labels = karyogramStateLabels();
const view = { kb: null, layout: null, worker: null, watchdog: null };

const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("en-US");

/** "reference-only" | "loading" | "result" | "error": read by tests and by the design handoff. */
function setViewState(name) {
  $("karyogram-main").setAttribute("data-karyogram-state", name);
}

function setInputsDisabled(disabled) {
  $("karyogram-file-input").disabled = disabled;
  $("btn-load-karyogram-sample").disabled = disabled;
}

function updateProgress(percent, message) {
  $("karyogram-progress-bar").style.width = `${percent}%`;
  $("karyogram-progress-pct").textContent = `${percent}%`;
  $("karyogram-progress-msg").textContent = message;
}

function hideTotals() {
  $("karyogram-totals").classList.add("hidden");
  $("karyogram-density-notice").classList.add("hidden");
}

function stateOf(layout, rsid) {
  return layout.sample ? layout.sample.observations[rsid] : "reference";
}

function renderLegend(layout) {
  const counts = Object.fromEntries(LEGEND_ORDER.map((s) => [s, 0]));
  for (const l of layout.reference.loci) counts[stateOf(layout, l.rsid)] += 1;
  $("karyogram-legend").innerHTML = LEGEND_ORDER.map(
    (s) =>
      `<li class="flex items-center gap-2" data-legend-state="${escapeHtml(s)}">` +
      `<span class="kary-swatch kary-state-${escapeHtml(s)}" aria-hidden="true"></span>` +
      `<span class="flex-1">${escapeHtml(labels[s])}</span>` +
      `<span class="font-bold" data-legend-count="${escapeHtml(s)}">${counts[s]}</span></li>`,
  ).join("");
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
    density: sample.density === "available" ? "Available" : "Unavailable",
  };
  for (const [name, text] of Object.entries(values)) {
    document.querySelector(`#karyogram-totals [data-total="${name}"]`).textContent = text;
  }
  $("karyogram-density-notice").classList.toggle("hidden", sample.density === "available");
  $("karyogram-totals").classList.remove("hidden");
}

function renderLoci(layout) {
  $("karyogram-loci-body").innerHTML = layout.reference.loci
    .map((l) => {
      const state = stateOf(layout, l.rsid);
      return (
        `<tr data-rsid="${escapeHtml(l.rsid)}" data-state="${escapeHtml(state)}">` +
        `<td>${escapeHtml(l.gene)}</td><td>${escapeHtml(l.rsid)}</td>` +
        `<td>${escapeHtml(l.chrom)}:${escapeHtml(fmt(l.pos))}</td>` +
        `<td>${escapeHtml(labels[state] ?? state)}</td></tr>`
      );
    })
    .join("");
}

function renderProvenance(layout) {
  const { build } = layout.geometry;
  const assembly = view.kb.assemblies[build];
  const tables = assembly.sources.map((s) => `${s.table} retrieved ${s.retrieved}`).join("; ");
  const assumed = layout.sample && layout.sample.density === "unavailable" ? " (the file's build is unknown)" : "";
  $("karyogram-provenance").textContent =
    `Geometry: ${build}${assumed}, UCSC ${assembly.ucsc} tables ${tables}. ` +
    `Knowledge base release ${view.kb.manifest.release}.`;
}

function render(layout) {
  view.layout = layout;
  $("karyogram-figure").innerHTML = renderKaryogramSvg(layout, { stateLabels: labels });
  renderLegend(layout);
  renderTotals(layout);
  renderLoci(layout);
  renderProvenance(layout);
}

/** The one error path: every failure shows #karyogram-error, drops any result and goes back to the reference view. */
function showError(message) {
  stopWorker();
  $("karyogram-progress").classList.add("hidden");
  $("karyogram-error-detail").textContent = String(message || "unknown error");
  $("karyogram-error").classList.remove("hidden");
  setInputsDisabled(false);
  setViewState("error");
  if (view.kb) {
    try {
      render(layoutKaryogram({ kb: view.kb }));
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

function startWorker() {
  stopWorker();
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  view.worker = worker;
  const fail = (message) => {
    if (view.worker === worker) showError(message);
  };
  worker.onerror = (err) => fail((err && err.message) || "The analysis worker failed to start.");
  worker.onmessageerror = () => fail("The analysis worker sent a message the page could not read.");
  worker.onmessage = (e) => {
    if (view.worker !== worker) return;
    const data = e.data;
    if (data.type === "progress") {
      armWatchdog(fail);
      updateProgress(data.percent, data.status);
    } else if (data.type === "karyogram") {
      stopWorker();
      try {
        render(data.layout);
        $("karyogram-progress").classList.add("hidden");
        setInputsDisabled(false);
        setViewState("result");
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

function processText(text, fileName) {
  $("karyogram-error").classList.add("hidden");
  setInputsDisabled(true);
  setViewState("loading");
  $("karyogram-progress").classList.remove("hidden");
  startWorker().postMessage({ action: "karyogram", text, fileName });
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

async function loadSample() {
  try {
    $("karyogram-error").classList.add("hidden");
    setViewState("loading");
    $("karyogram-progress").classList.remove("hidden");
    updateProgress(10, "Fetching the synthetic karyogram sample...");
    const resp = await fetch(SAMPLE_URL);
    if (!resp.ok) throw new Error("Could not load the synthetic sample file.");
    processText(await resp.text(), SAMPLE_NAME);
  } catch (err) {
    showError((err && err.message) || err);
  }
}

async function initPage() {
  initTheme();
  window.__lucidaseKaryogram = {
    get layout() {
      return view.layout;
    },
  };
  const fileInput = $("karyogram-file-input");
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFileSelected(e.target.files[0]);
    fileInput.value = "";
  });
  $("btn-load-karyogram-sample").addEventListener("click", loadSample);
  try {
    view.kb = await loadKnowledgeBase();
    render(layoutKaryogram({ kb: view.kb }));
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
