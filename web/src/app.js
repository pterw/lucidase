/**
 * Lucidase - Main Frontend Application Logic
 * =============================================
 * Orchestrates Web Worker file parsing, reactive UI updates,
 * compound APOE diplotype synthesis, light/dark mode theming,
 * filtering, sorting and the variant inspection drawer.
 *
 * Every table row, drawer field and export value comes from view-model.js (one display model per
 * record); this file owns the DOM only. Any record or KB value placed in an innerHTML string goes
 * through escapeHtml.
 */

import { offspringDistribution, geneOutcome, penetranceAdjustedAffected } from "./core/inheritance.js";
import { loadKnowledgeBase } from "./kb-loader.js";
import { getTheme, initTheme, setTheme } from "./theme.js";
import { initPagesMenu } from "./pages-menu.js";
import { renderKaryogramSvg } from "./karyogram-view.js";
import {
  NOT_AVAILABLE,
  acmgVersionLabel,
  apoeCardModel,
  csvReport,
  drawerTierText,
  escapeHtml,
  fmtPct,
  formatRate,
  foundCategoryCounts,
  groupedReport,
  heroScopeText,
  karyogramStateLabels,
  kbBadge,
  markdownReport,
  multiLocusReading,
  partnerModelNote,
  rowsByState,
  summaryProse,
  testedVariantCounts,
  toViewModel,
  MODEL_LABELS,
  RESULT_WORDS,
} from "./view-model.js";

// Global Application State
const state = {
  worker: null,
  watchdog: null,
  workerTimeoutMs: 30000,
  fileName: "",
  qc: null,
  records: [],
  negativeChecks: [],
  arrayGaps: [],
  insufficientEvidence: [],
  coverageSummary: null,
  summary: null,
  apoe: null,
  manifest: null,
  genes: {},
  compoundHeterozygotes: [],
  independentAssortment: [],
  // The Summary map's layout (core/karyogram.js), and the analysis that waits for it while the worker lays it out.
  karyogram: null,
  pendingAnalysis: null,
  selectedVariant: null,
  filterCategory: "all",
  searchQuery: "",
  sortBy: "magnitude",
  // The StepNav step (0 choose your file, 1 read your results, 2 save a copy), set by the page phase.
  step: 0,
  // Read-only view of the theme owned by theme.js (its storage reads and writes are guarded there).
  get theme() {
    return getTheme();
  }
};

// The StepNav's three steps (declared before initApp runs, which may be at module evaluation).
const STEPS = ["Choose your file", "Read your results", "Save a copy"];

// The last stretch of the progress bar: the worker reads the file again to lay out the Summary map.
const MAP_PROGRESS = { percent: 95, status: "Placing the checks on the map of your chromosomes" };

// Initialize Application (handles both pre- and post-DOMContentLoaded module execution)
function initApp() {
  console.log("initApp executed, readyState:", document.readyState);
  initTheme();
  initPagesMenu();
  initEventListeners();
  renderStepNav();
  loadManifest();
  window.__lucidase = {
    state,
    processText,
    exportMarkdownReport,
    exportCsvReport,
    setTheme
  };
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

// A value the record or the KB does not carry is shown as "Not available" in a muted style, never as a placeholder.
const MUTED = "lds-na-text";
const naHtml = (text = NOT_AVAILABLE) => `<span class="${MUTED}">${escapeHtml(text)}</span>`;
const valueHtml = (value, naText) => (value === null || value === undefined ? naHtml(naText) : escapeHtml(value));

function setValue(el, value, naText = NOT_AVAILABLE) {
  if (!el) return;
  if (value === null || value === undefined) {
    const span = document.createElement("span");
    span.className = MUTED;
    span.textContent = naText;
    el.replaceChildren(span);
  } else {
    el.textContent = value;
  }
}

/** The KB claims on the page (release badge, ACMG SF scope) come from the KB manifest, never from literals. */
function renderKbClaims(manifest) {
  const badge = kbBadge(manifest);
  const badgeEl = document.getElementById("kb-provenance-badge");
  const textEl = document.getElementById("kb-provenance-text");
  if (badgeEl) badgeEl.title = badge.title;
  if (textEl) textEl.textContent = badge.text;
  const hero = document.getElementById("hero-scope");
  if (hero) hero.textContent = heroScopeText(manifest);
  document.querySelectorAll("[data-acmg-version]").forEach((el) => {
    el.textContent = acmgVersionLabel(manifest);
  });
}

/** Reads the manifest from the KB the worker loads and validates (kb-loader.js), so the page claims match the analysis. */
async function loadManifest() {
  try {
    const kb = await loadKnowledgeBase();
    renderKbClaims(kb.manifest);
  } catch (err) {
    // A KB that cannot be loaded or fails validation makes no claims: the page reads "Not available".
    console.error(err && err.message ? err.message : err);
    renderKbClaims(null);
  }
}

// One worker per analysis run: a worker that failed (or never answers) is
// terminated and the next run starts fresh, so a retry can never hang on a dead one.
// A worker whose module graph fails to load (a dropped request, a machine out of socket buffers)
// raises an error event with no message before it has answered anything. That is a transient start
// failure, so the run starts one fresh worker with the same job; a worker that throws, or fails
// twice, takes the error path.
function startWorker(job, canRetry = true) {
  stopWorker();
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  state.worker = worker;
  let answered = false;
  const fail = (message) => {
    if (state.worker !== worker) return;
    stopWorker();
    showAnalysisError(message);
  };

  worker.onerror = (err) => {
    if (canRetry && !answered && state.worker === worker && !(err && err.message)) {
      try {
        startWorker(job, false).postMessage(job);
        return;
      } catch (retryErr) {
        stopWorker();
        showAnalysisError((retryErr && retryErr.message) || "The analysis worker failed to start.");
        return;
      }
    }
    fail((err && err.message) || "The analysis worker failed to start.");
  };
  worker.onmessageerror = () => {
    fail("The analysis worker sent a message the page could not read.");
  };
  worker.onmessage = (e) => {
    if (state.worker !== worker) return;
    answered = true;
    clearWatchdog();
    const data = e.data;
    if (data.type === "progress") {
      armWatchdog(fail);
      if (job.action === "karyogram") updateProgress(MAP_PROGRESS.percent, MAP_PROGRESS.status);
      else updateProgress(data.percent, data.status);
    } else if (data.type === "complete") {
      // The results wait for the Summary map: the same file goes to the worker's own "karyogram" action (the one
      // karyogram.html uses), so the map is laid out exactly as on that page. Its failure is the analysis's failure.
      try {
        state.pendingAnalysis = data;
        const mapJob = { action: "karyogram", text: job.text, fileName: job.fileName };
        updateProgress(MAP_PROGRESS.percent, MAP_PROGRESS.status);
        startWorker(mapJob).postMessage(mapJob);
      } catch (err) {
        stopWorker();
        showAnalysisError((err && err.message) || err);
      }
    } else if (data.type === "karyogram") {
      stopWorker();
      const analysis = state.pendingAnalysis;
      state.pendingAnalysis = null;
      try {
        if (!analysis) throw new Error("The map arrived without the analysis it belongs to.");
        handleParseComplete(analysis, data.layout);
      } catch (err) {
        showAnalysisError((err && err.message) || err);
      }
    } else if (data.type === "error") {
      fail(data.message);
    }
  };
  armWatchdog(fail);
  return worker;
}

// Inactivity watchdog: re-armed on start and on every progress message, so a worker
// that stalls or dies silently at any point fails visibly. Complete/error/stop clear it.
function armWatchdog(fail) {
  clearWatchdog();
  state.watchdog = setTimeout(
    () => fail("The analysis worker stopped responding."),
    state.workerTimeoutMs
  );
}

function clearWatchdog() {
  if (state.watchdog) clearTimeout(state.watchdog);
  state.watchdog = null;
}

function stopWorker() {
  clearWatchdog();
  if (state.worker) state.worker.terminate();
  state.worker = null;
}

function setInputsDisabled(disabled) {
  const fileInput = document.getElementById("file-input");
  const btnDemo = document.getElementById("btn-load-demo");
  if (fileInput) fileInput.disabled = disabled;
  if (btnDemo) btnDemo.disabled = disabled;
}

// The one error path: every failure (worker, KB, file read, demo fetch) shows the #analysis-error alert and no results.
function showAnalysisError(message) {
  closeDrawer();
  state.pendingAnalysis = null;
  document.getElementById("progress-section").classList.add("hidden");
  document.getElementById("results-section").classList.add("hidden");
  const box = document.getElementById("analysis-error");
  document.getElementById("analysis-error-detail").textContent =
    String(message || "unknown error");
  box.classList.remove("hidden");
  setInputsDisabled(false);
  showIntro(true);
  setStep(0);
}

function initEventListeners() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const btnDemo = document.getElementById("btn-load-demo");
  const searchInput = document.getElementById("search-input");
  const filterButtons = document.querySelectorAll("[data-filter]");
  const btnExportMd = document.getElementById("btn-export-md");
  const btnExportCsv = document.getElementById("btn-export-csv");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");

  // Drag and drop
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-over");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-over");
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-over");
    if (e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  // File selector
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });

  const btnBrowse = document.getElementById("btn-browse-files");
  if (btnBrowse) {
    btnBrowse.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.click();
    });
  }

  // Click dropzone area outside buttons to open file dialog
  dropzone.addEventListener("click", (e) => {
    if (e.target.closest("button") || e.target.closest("a")) return;
    fileInput.click();
  });

  if (btnDemo) {
    btnDemo.addEventListener("click", async () => {
      try {
        updateProgress(10, "Loading the made-up example file");
        const resp = await fetch("./demo-data/sample-23andme.txt");
        if (!resp.ok) throw new Error("Could not load sample file.");
        const text = await resp.text();
        state.fileName = "sample-23andme.txt";
        processText(text, state.fileName);
      } catch (err) {
        showAnalysisError(err.message);
      }
    });
  }

  // The grouped report: "Details" opens the record in the drawer, the same way a table row does.
  document.getElementById("report-groups").addEventListener("click", (e) => {
    const button = e.target.closest("button.lds-finding-open");
    if (!button) return;
    const id = button.closest("article.lds-finding").dataset.findingId;
    const record = allRows().find((vm) => vm.id === id);
    if (record) openDrawer(record, button);
  });

  // The Summary map: a mark opens its record (click, or Enter / Space on the focused mark).
  const summaryMap = document.getElementById("summary-map");
  summaryMap.addEventListener("click", (e) => {
    const mark = e.target.closest(".kary-locus[data-finding-id]");
    if (mark) openMarkRecord(mark);
  });
  summaryMap.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const mark = e.target.closest(".kary-locus[data-finding-id]");
    if (!mark || mark !== e.target) return;
    e.preventDefault(); // Space must open the record, not scroll the page
    openMarkRecord(mark);
  });

  // "All results as a table" opens once asked for (design system: the button gives way to the table).
  document.getElementById("btn-show-table").addEventListener("click", () => {
    setTableOpen(true);
    searchInput.focus();
  });

  // Search input
  searchInput.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    renderVariantsTable();
  });

  // Filter tabs
  const markActiveFilter = (active) => filterButtons.forEach(b => {
    b.classList.toggle("tab-active", b === active);
    b.setAttribute("aria-pressed", String(b === active));
  });
  markActiveFilter(document.querySelector("[data-filter].tab-active"));
  filterButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      markActiveFilter(btn);
      state.filterCategory = btn.getAttribute("data-filter");
      renderVariantsTable();
    });
  });

  // Exports: using the save section is step 3.
  btnExportMd.addEventListener("click", () => {
    enterSaveStep();
    exportMarkdownReport();
  });
  btnExportCsv.addEventListener("click", () => {
    enterSaveStep();
    exportCsvReport();
  });
  document.getElementById("save").addEventListener("focusin", enterSaveStep);

  // Steps: the StepNav (both forms) and the two buttons by the results heading.
  document.getElementById("stepnav").addEventListener("click", (e) => {
    const button = e.target.closest("button[data-step]");
    if (button) goToStep(Number(button.dataset.step));
  });
  document.getElementById("btn-goto-save").addEventListener("click", () => goToStep(2));
  document.getElementById("btn-use-another-file").addEventListener("click", () => goToStep(0));


  // Inspector close: its close button, or Escape anywhere on the page while it is open (design system Inspector)
  if (btnCloseDrawer) {
    btnCloseDrawer.addEventListener("click", closeDrawer);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.selectedVariant !== null) closeDrawer();
  });
}

function handleFileSelected(file) {
  state.fileName = file.name;
  updateProgress(5, `Reading ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`);

  const reader = new FileReader();
  reader.onload = (e) => {
    processText(e.target.result, file.name);
  };
  reader.onerror = () => {
    showAnalysisError("Failed to read file from disk.");
  };
  reader.readAsText(file);
}

// Both entry points (file and demo) start here, so a synchronous start failure (a throwing
// Worker constructor or postMessage) takes the one error path instead of leaving inputs disabled.
function processText(text, fileName) {
  try {
    closeDrawer();
    state.pendingAnalysis = null;
    document.getElementById("analysis-error").classList.add("hidden");
    setInputsDisabled(true);
    document.getElementById("progress-section").classList.remove("hidden");
    document.getElementById("results-section").classList.add("hidden");
    showIntro(true);
    setStep(0);
    const job = { action: "parse", text, fileName };
    startWorker(job).postMessage(job);
  } catch (err) {
    stopWorker();
    showAnalysisError((err && err.message) || err);
  }
}

function updateProgress(percent, message) {
  const bar = document.getElementById("parse-progress-bar");
  const msg = document.getElementById("parse-progress-msg");
  const pct = document.getElementById("parse-progress-pct");
  // The bar grows by transform only (the design system's motion rule).
  if (bar) bar.style.transform = `scaleX(${Math.min(100, Math.max(0, percent)) / 100})`;
  if (msg) msg.textContent = message;
  if (pct) pct.textContent = `${percent}%`;
}

function handleParseComplete(data, karyogram) {
  const listed = [...data.records, ...data.negative_checks, ...data.array_gaps, ...data.insufficient_evidence];
  if (data.apoe) listed.push(data.apoe);
  const testedCounts = testedVariantCounts(listed);
  const toVm = (record) => toViewModel(record, data.genes, testedCounts);

  state.manifest = data.manifest;
  state.genes = data.genes;
  state.qc = data.qc;
  state.records = data.records.map(toVm);
  state.negativeChecks = data.negative_checks.map(toVm);
  state.arrayGaps = data.array_gaps.map(toVm);
  state.insufficientEvidence = data.insufficient_evidence.map(toVm);
  state.coverageSummary = data.coverage_taxonomy;
  state.summary = data.summary;
  state.apoe = data.apoe ? toVm(data.apoe) : null;
  state.compoundHeterozygotes = data.compound_heterozygotes;
  state.independentAssortment = data.independent_assortment;
  state.karyogram = karyogram;

  document.getElementById("progress-section").classList.add("hidden");
  document.getElementById("analysis-error").classList.add("hidden");
  document.getElementById("results-section").classList.remove("hidden");
  setInputsDisabled(false);
  // The intro gives way to the results. A control in it that held focus (the example button) is gone, so focus
  // moves to the results heading instead of falling back to the page.
  const focusWasInIntro = document.getElementById("section-hero").contains(document.activeElement);
  showIntro(false);
  setStep(1);
  if (focusWasInIntro) document.getElementById("results-h").focus();

  renderKbClaims(state.manifest);
  renderQC();
  renderSummaryCards();
  renderReportGroups();
  renderAssortmentSection();
  setTableOpen(false);
  renderVariantsTable();
}

/** Opens or closes "All results as a table". Closed, only the "Show the table" button is shown. */
function setTableOpen(open) {
  const button = document.getElementById("btn-show-table");
  button.setAttribute("aria-expanded", String(open));
  button.classList.toggle("hidden", open);
  document.getElementById("table-panel").classList.toggle("hidden", !open);
}

/**
 * The grouped report (design system): one ReportSection per group, in its order, each with one FindingRow per
 * check (view-model.js groupedReport). The mark keeps its shape and carries the plain word, so colour is never the
 * only signal; the limitation is always on the row. A group with no check says so instead of disappearing.
 */
function renderReportGroups() {
  const container = document.getElementById("report-groups");
  container.innerHTML = groupedReport(allRows(), state.genes).map((group) => `
    <section id="group-${escapeHtml(group.id)}" class="lds-section" aria-labelledby="group-${escapeHtml(group.id)}-h">
      <div class="lds-section-head">
        <h2 id="group-${escapeHtml(group.id)}-h" class="lds-section-title">${escapeHtml(group.title)}</h2>
        <p class="lds-section-aside">${escapeHtml(group.aside)}</p>
      </div>
      <div class="lds-section-body">
        ${group.rows.length === 0 ? `<p class="lds-meta">No checks in this group.</p>` : group.rows.map(findingRowHtml).join("")}
      </div>
    </section>
  `).join("");
}

function findingRowHtml(row) {
  const headingId = `f-${escapeHtml(row.key)}-h`;
  const limitation = row.limitation === null
    ? ""
    : `<p class="lds-finding-limit"><span class="lds-icon lds-i-info" aria-hidden="true"></span><span><b>What this can’t tell you:</b> ${escapeHtml(row.limitation)}</span></p>`;
  return `
    <article class="lds-finding" aria-labelledby="${headingId}" data-finding-id="${escapeHtml(row.id)}">
      <span class="lds-mark lds-mark-16 lds-mark-${escapeHtml(row.state)}" role="img" aria-label="${escapeHtml(row.stateLabel)}"></span>
      <div class="lds-finding-main">
        <div class="lds-finding-head">
          <h3 id="${headingId}" class="lds-finding-topic">${escapeHtml(row.topic)}</h3>
          <span class="lds-finding-gene">${escapeHtml(row.gene)}</span>
        </div>
        <p class="lds-finding-statement">${escapeHtml(row.statement)}</p>
        ${limitation}
        <div class="lds-finding-tech">${escapeHtml(row.technical)}</div>
      </div>
      <button type="button" class="lds-finding-open" aria-controls="variant-drawer" aria-expanded="false" aria-label="Details for ${escapeHtml(row.topic)}, ${escapeHtml(row.markers)}">Details<span class="lds-icon lds-i-chevron-right" aria-hidden="true"></span></button>
    </article>`;
}

/**
 * The FindingRow whose record is in the drawer is the one selected row (none when the drawer is closed), and its
 * marks on the Summary map are the selected marks (APOE has two).
 */
function markSelectedFinding(id) {
  document.querySelectorAll("#report-groups article.lds-finding").forEach((article) => {
    const selected = article.dataset.findingId === id;
    article.classList.toggle("is-selected", selected);
    article.querySelector("button.lds-finding-open").setAttribute("aria-expanded", String(selected));
  });
  document.querySelectorAll("#summary-map .kary-locus[data-finding-id]").forEach((mark) => {
    const selected = mark.dataset.findingId === id;
    mark.classList.toggle("is-selected", selected);
    mark.setAttribute("aria-expanded", String(selected));
  });
}

// StepNav (design system): the step follows the page phase. Reading, or failing to read, a file is step 1; the
// results are step 2; the save section is step 3. Step 1 can always be revisited, steps 2 and 3 only once there are
// results. Both forms (the list, and the narrow "Step N of 3") are in the markup; a container query shows one.
function setStep(step) {
  state.step = step;
  renderStepNav();
}

function renderStepNav() {
  const nav = document.getElementById("stepnav");
  if (!nav) return;
  const current = state.step;
  const hasResults = current > 0;
  nav.querySelector(".lds-stepnav-list").innerHTML = STEPS.map((label, i) => {
    const status = i < current ? "done" : i === current ? "current" : "upcoming";
    const dot = status === "done" ? `<span class="lds-icon lds-icon-14 lds-i-check"></span>` : String(i + 1);
    const done = status === "done" ? `<span class="sr-only"> (done)</span>` : "";
    const inner = `<span class="lds-step-dot" aria-hidden="true">${dot}</span><span>${escapeHtml(label)}${done}</span>`;
    const canVisit = status !== "current" && (i === 0 || hasResults);
    const item = canVisit
      ? `<button type="button" class="lds-step-item" data-step="${i}">${inner}</button>`
      : `<span class="lds-step-item"${status === "current" ? ` aria-current="step"` : ""}>${inner}</span>`;
    const line = i < STEPS.length - 1 ? `<span class="lds-step-line" aria-hidden="true"></span>` : "";
    return `<li class="lds-step" data-state="${status}">${item}${line}</li>`;
  }).join("");

  // Narrow form: the current step, "Step N of 3", a bar grown by transform, and a link back to the previous step.
  nav.querySelector(".lds-stepnav-current").textContent = STEPS[current];
  nav.querySelector(".lds-stepnav-count").textContent = `Step ${current + 1} of ${STEPS.length}`;
  nav.querySelector(".lds-progress-bar").style.transform = `scaleX(${(current + 1) / STEPS.length})`;
  const back = nav.querySelector(".lds-stepnav-back");
  back.hidden = current === 0;
  if (current > 0) {
    back.dataset.step = String(current - 1);
    back.querySelector("[data-role='back-label']").textContent = STEPS[current - 1];
  }
}

/** A visit from the StepNav or the results heading. Step 1 returns to the file chooser; steps 2 and 3 need results. */
function goToStep(step) {
  if (step === 0) {
    useAnotherFile();
    return;
  }
  if (state.step === 0) return;
  setStep(step);
  document.getElementById(step === 2 ? "save-h" : "results-h").focus();
}

/** The person reached the save section (used a button in it, or moved focus into it). */
function enterSaveStep() {
  if (state.step === 1) setStep(2);
}

function showIntro(show) {
  document.getElementById("section-hero").classList.toggle("hidden", !show);
}

/**
 * Back to the file chooser. The previous file's results leave the page and memory, so nothing of it is left to show
 * or export, and the intro returns with focus on "Choose your DNA file". The KB claims stay.
 */
function useAnotherFile() {
  closeDrawer();
  Object.assign(state, {
    fileName: "",
    qc: null,
    records: [],
    negativeChecks: [],
    arrayGaps: [],
    insufficientEvidence: [],
    coverageSummary: null,
    summary: null,
    apoe: null,
    compoundHeterozygotes: [],
    independentAssortment: [],
    karyogram: null,
    pendingAnalysis: null,
  });
  document.getElementById("variants-tbody").replaceChildren();
  document.getElementById("summary-map").replaceChildren();
  document.getElementById("report-groups").replaceChildren();
  document.getElementById("assortment-cards-container").replaceChildren();
  document.getElementById("results-section").classList.add("hidden");
  document.getElementById("analysis-error").classList.add("hidden");
  document.getElementById("progress-section").classList.add("hidden");
  document.getElementById("file-input").value = "";
  showIntro(true);
  setStep(0);
  window.scrollTo(0, 0);
  document.getElementById("btn-browse-files").focus({ preventScroll: true });
}

function renderQC() {
  const qc = state.qc;
  if (!qc) return;

  document.getElementById("qc-filename").textContent = state.fileName;
  document.getElementById("qc-format").textContent = `${qc.format_name.toUpperCase()} (${qc.build})`;
  document.getElementById("qc-total-snps").textContent = qc.total_snps.toLocaleString();
  // A null rate (variants-only VCF) is shown as "Not available", with the QC note as a tooltip.
  setValue(document.getElementById("qc-call-rate"), qc.call_rate === null ? null : formatRate(qc.call_rate));
  setValue(document.getElementById("qc-het-rate"), qc.heterozygosity_rate === null ? null : formatRate(qc.heterozygosity_rate));
  for (const id of ["qc-call-rate", "qc-het-rate"]) document.getElementById(id).title = qc.qc_note ?? "";

  // The badge shows the QC signal verbatim; it makes no sex or karyotype claim.
  const sexBadge = document.getElementById("qc-inferred-sex");
  sexBadge.textContent = qc.sex_signal;
  sexBadge.title = `X markers: ${qc.x_markers.toLocaleString()} | X heterozygosity: ${(qc.x_het_rate * 100).toFixed(1)}% | Y calls: ${qc.y_calls.toLocaleString()}`;
  sexBadge.className = `lds-tag ${NEUTRAL_TAG}`;
}

/**
 * The result counts are the worker's coverage figures. The category counts sit under "What was found", so the view
 * model counts them over the Found checks only (the worker's summary also counts unclear variant readings).
 */
function renderSummaryCards() {
  const cov = state.coverageSummary;
  if (!state.summary || !cov) return;
  const figure = (value) => (typeof value === "number" ? value.toLocaleString() : NOT_AVAILABLE);
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = figure(value);
  };

  const found = foundCategoryCounts(listedRows());
  set("count-pathogenic", found.pathogenic);
  set("count-carrier", found.carrier);
  set("count-pgx", found.pgx);
  set("count-risk", found.risk);
  set("count-acmg", found.acmg);

  // The sentence and the legend say the same figures: the worker's count per result.
  const counts = {
    supported_and_observed: cov.supported_and_observed_count,
    supported_not_observed: cov.supported_not_observed_count,
    not_tested_by_array: cov.not_tested_by_array_count,
    insufficient_evidence: cov.insufficient_evidence_count,
    outside_coverage: cov.outside_coverage_count,
  };
  document.getElementById("summary-prose").textContent = summaryProse(counts);
  renderSummaryLegend(counts);
  renderSummaryMap(state.karyogram);
}

// The legend's results in the design system's order (AnalysisScreen), each count keeping the id the tests and the
// earlier count strip used. "Not checked" has no mark on the map: it counts the file's other markers.
const SUMMARY_LEGEND = [
  ["supported_and_observed", "count-state-observed"],
  ["supported_not_observed", "count-state-negative"],
  ["not_tested_by_array", "count-state-gaps"],
  ["insufficient_evidence", "count-state-insufficient"],
  ["outside_coverage", "count-state-outside"],
];

/** The KaryogramLegend (design system): mark and plain word, the count, and the word's one-line help. */
function renderSummaryLegend(counts) {
  document.getElementById("summary-legend").innerHTML = SUMMARY_LEGEND.map(([s, id]) => `
    <li class="lds-legend-item" data-legend-state="${escapeHtml(s)}">
      <span class="lds-statemark"><span class="lds-mark lds-mark-14 lds-mark-${escapeHtml(s)}" aria-hidden="true"></span>${escapeHtml(RESULT_WORDS[s].label)}</span>
      <span id="${escapeHtml(id)}" class="lds-legend-count" data-legend-count="${escapeHtml(s)}">${escapeHtml(counts[s].toLocaleString())}</span>
      <span class="lds-legend-help">${escapeHtml(RESULT_WORDS[s].help)}</span>
    </li>`).join("");
}

/**
 * The Summary map (design system Karyogram): the karyogram page's own view of the layout, with each checked locus
 * made a button that opens its record in the Inspector. A locus belongs to the listed record with its rsid, or to the
 * APOE record when it is one of its components; a locus with no record is a bug upstream and throws (fail fast).
 * The figure becomes a group, not an image, so its buttons stay visible to assistive technology.
 */
function renderSummaryMap(layout) {
  const box = document.getElementById("summary-map");
  if (!layout) throw new Error("The analysis has no map layout.");
  box.innerHTML = renderKaryogramSvg(layout, { stateLabels: karyogramStateLabels() });
  box.querySelector("svg").setAttribute("role", "group");
  document.getElementById("summary-density-notice").classList.toggle("hidden", layout.sample.density === "available");

  const recordOf = new Map();
  for (const vm of allRows()) for (const locus of vm.components ?? [vm]) recordOf.set(locus.rsid, vm);
  box.querySelectorAll(".kary-locus").forEach((mark) => {
    const rsid = mark.dataset.rsid;
    const record = recordOf.get(rsid);
    if (!record) throw new Error(`The map has a mark for ${rsid}, which no result carries.`);
    const gene = state.genes[record.gene];
    const topic = gene && typeof gene.topic === "string" && gene.topic !== "" ? gene.topic : record.gene;
    const markState = mark.dataset.state;
    if (!Object.hasOwn(RESULT_WORDS, markState)) throw new Error(`The map has an unknown result "${markState}" for ${rsid}.`);
    mark.dataset.findingId = record.id;
    mark.setAttribute("tabindex", "0");
    mark.setAttribute("role", "button");
    mark.setAttribute("aria-controls", "variant-drawer");
    mark.setAttribute("aria-expanded", "false");
    mark.setAttribute("aria-label", `${topic}, ${rsid}: ${RESULT_WORDS[markState].label}`);
  });
}

/** Selecting a mark (click, Enter or Space) opens its record, the same way a FindingRow's Details button does. */
function openMarkRecord(mark) {
  const record = allRows().find((vm) => vm.id === mark.dataset.findingId);
  if (record) openDrawer(record, mark);
}

// Badge tones (styles.css, from the design system's colour tokens). Each label is styled by an explicit map; anything
// the page has no style for (an unknown category, tier or state) is the one neutral tone, never a "good" (green) one.
const NEUTRAL_TAG = "lds-tag-neutral";

// Each marker of a multi-locus finding with its own result word and StateMark, so colour is never the only signal,
// and the caution line when one of them is not Found (owner ruling 2026-10-04).
function multiLocusComponentsHtml(finding) {
  const { components, caution } = multiLocusReading(finding, state.records);
  const items = components.map((c) => `
    <li class="flex items-center gap-2" data-component-rsid="${escapeHtml(c.rsid)}">
      <span class="lds-data">${escapeHtml(c.rsid)}</span>${stateTagHtml(c.state, c.label)}
    </li>`).join("");
  const cautionHtml = caution === null
    ? ""
    : `<p class="lds-finding-limit"><span class="lds-icon lds-i-info" aria-hidden="true"></span><span>${escapeHtml(caution)}</span></p>`;
  return `<ul class="flex flex-wrap gap-x-6 gap-y-2" aria-label="Result per marker">${items}</ul>${cautionHtml}`;
}

function renderAssortmentSection() {
  const section = document.getElementById("assortment-section");
  const container = document.getElementById("assortment-cards-container");
  const badge = document.getElementById("assortment-findings-count-badge");
  if (!section || !container) return;

  const compounds = state.compoundHeterozygotes;
  const assortments = state.independentAssortment;
  const totalFindings = compounds.length + assortments.length;

  if (totalFindings === 0) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  if (badge) {
    badge.textContent = `${totalFindings} multi-locus finding${totalFindings === 1 ? '' : 's'}`;
  }
  container.innerHTML = "";

  // One row per finding, hairlines between (no nested cards). Every interpolated value is escaped.
  const ROW = "flex flex-col gap-3 py-5 border-b border-line first:pt-0";

  // Possible compound heterozygotes (e.g. HFE C282Y / H63D).
  compounds.forEach(ch => {
    const row = document.createElement("div");
    row.className = ROW;
    row.innerHTML = `
      <div class="flex flex-wrap items-center gap-2">
        <span class="lds-h3">Possible compound heterozygote · phase unknown</span>
        <span class="lds-tag lds-tag-cat-pathogenic">${escapeHtml(ch.significance)}</span>
        <span class="lds-tag ${NEUTRAL_TAG} lds-data">${escapeHtml(ch.gene)}</span>
      </div>
      <div class="flex flex-col gap-1">
        <p class="lds-h3 lds-data">${escapeHtml(ch.title)}</p>
        <p class="lds-prose">${escapeHtml(ch.summary)}</p>
      </div>
      ${multiLocusComponentsHtml(ch)}
      <p class="lds-meta"><strong class="text-ink">Segregation:</strong> ${escapeHtml(ch.segregation_notes)}</p>
      <div>
        <button type="button" class="lds-btn lds-btn-secondary lds-btn-xs btn-inspect-gene" data-gene="${escapeHtml(ch.gene)}">
          See the ${escapeHtml(ch.gene)} details
        </button>
      </div>
    `;
    container.appendChild(row);
  });

  // Co-occurring variant alleles on unlinked loci (e.g. F5 chr 1 + F2 chr 11).
  assortments.forEach(ia => {
    const row = document.createElement("div");
    row.className = ROW;
    row.innerHTML = `
      <div class="flex flex-wrap items-center gap-2">
        <span class="lds-h3">Co-occurring variant alleles</span>
        <span class="lds-tag lds-tag-cat-risk">Multi-locus</span>
        <span class="lds-tag ${NEUTRAL_TAG} lds-data">${escapeHtml(ia.genes.join(" + "))}</span>
      </div>
      <div class="flex flex-col gap-1">
        <p class="lds-h3">${escapeHtml(ia.type)}</p>
        <p class="lds-prose">${escapeHtml(ia.description)}</p>
      </div>
      ${multiLocusComponentsHtml(ia)}
      <dl class="lds-datalist">
        <div><dt>Loci on different chromosomes</dt><dd>${escapeHtml(ia.loci.join(" · "))}</dd></div>
        <div><dt>Child inherits all listed alleles</dt><dd title="${escapeHtml(ia.assumption)}">${Math.round(ia.joint_transmission_prob * 100)}%</dd></div>
      </dl>
      <div class="flex flex-wrap gap-2">
        ${ia.genes.map(g => `
          <button type="button" class="lds-btn lds-btn-secondary lds-btn-xs btn-inspect-gene" data-gene="${escapeHtml(g)}">
            See the ${escapeHtml(g)} details
          </button>
        `).join("")}
      </div>
    `;
    container.appendChild(row);
  });

  // Attach inspection handlers
  container.querySelectorAll(".btn-inspect-gene").forEach(btn => {
    btn.addEventListener("click", () => {
      const g = btn.getAttribute("data-gene");
      const rec = state.records.find(r => r.gene === g);
      if (rec) openDrawer(rec);
    });
  });
}

// The coverage state as a tag with its shape-coded mark (the karyogram's dot language), so it reads without colour.
const STATE_TAG_CLASS = {
  supported_and_observed: "lds-tag-state-supported_and_observed",
  supported_not_observed: "lds-tag-state-supported_not_observed",
  not_tested_by_array: "lds-tag-state-not_tested_by_array",
  outside_coverage: "lds-tag-state-outside_coverage",
  insufficient_evidence: "lds-tag-state-insufficient_evidence"
};
const stateTagClass = (state) => `lds-tag ${Object.hasOwn(STATE_TAG_CLASS, state) ? STATE_TAG_CLASS[state] : NEUTRAL_TAG}`;
const stateTagInnerHtml = (state, text) =>
  (Object.hasOwn(STATE_TAG_CLASS, state) ? `<span class="lds-mark lds-mark-${state}" aria-hidden="true"></span>` : "") + escapeHtml(text);
const stateTagHtml = (state, text) => `<span class="${stateTagClass(state)}">${stateTagInnerHtml(state, text)}</span>`;

// The six KB categories each have their own tone (the design system's category colours). A Carrier flag on the row
// also gets the carrier tone. Anything else (a category added later) is neutral.
const CATEGORY_TAG_CLASS = {
  Pathogenic: "lds-tag-cat-pathogenic",
  Carrier: "lds-tag-cat-carrier",
  Pharmacogenomics: "lds-tag-cat-pgx",
  "Risk Factor": "lds-tag-cat-risk",
  Trait: "lds-tag-cat-trait",
  "Not detected": "lds-tag-cat-not-detected"
};
const categoryTagClass = (r) =>
  (Object.hasOwn(CATEGORY_TAG_CLASS, r.category) ? CATEGORY_TAG_CLASS[r.category] : null) ??
  (r.isCarrier ? CATEGORY_TAG_CLASS.Carrier : NEUTRAL_TAG);

// Evidence tiers are text in one neutral tone: a tier is not a result, so it gets no result colour.
const TIER_TAG_CLASS = `lds-tag ${NEUTRAL_TAG} lds-data`;

// The table's tabs named by a result word, and the state each lists. Every other tab is a category of Found checks.
const STATE_TABS = {
  all: "supported_and_observed",
  negative: "supported_not_observed",
  gaps: "not_tested_by_array",
  insufficient: "insufficient_evidence"
};

/** The worker's lists as view models, as received: they overlap (an unclear check is in two). */
function listedRows() {
  return [...state.records, ...state.negativeChecks, ...state.arrayGaps, ...state.insufficientEvidence];
}

function renderVariantsTable() {
  const tbody = document.getElementById("variants-tbody");
  tbody.innerHTML = "";

  // A tab named by a result word lists exactly the checks with that word; the category tabs narrow the Found ones.
  const byState = rowsByState(listedRows());
  const dataset = byState[Object.hasOwn(STATE_TABS, state.filterCategory) ? STATE_TABS[state.filterCategory] : "supported_and_observed"];

  const filtered = dataset.filter(r => {
    // Category filter for subcategories of the Found checks
    if (state.filterCategory === "pathogenic" && r.category !== "Pathogenic") return false;
    if (state.filterCategory === "carrier" && (r.category !== "Carrier" && !r.isCarrier)) return false;
    if (state.filterCategory === "pgx" && r.category !== "Pharmacogenomics") return false;
    if (state.filterCategory === "risk" && !r.riskFilter) return false;
    if (state.filterCategory === "acmg" && !r.acmg_actionable) return false;

    // Search query
    if (state.searchQuery) {
      const q = state.searchQuery;
      const match = [r.id, r.gene, r.phenotype, r.genotype, r.category, r.significance, r.drug_response, r.diplotype, r.diplotypeDisplay]
        .some(field => typeof field === "string" && field.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });

  let countLabel = `Showing ${filtered.length} of ${byState.supported_and_observed.length} findings`;
  if (state.filterCategory === "negative") {
    countLabel = `Showing ${filtered.length} loci checked where the variant was not found`;
  } else if (state.filterCategory === "gaps") {
    countLabel = `Showing ${filtered.length} loci your chip did not read`;
  } else if (state.filterCategory === "insufficient") {
    countLabel = `Showing ${filtered.length} loci with an unclear result`;
  }
  document.getElementById("showing-count").textContent = countLabel;

  if (filtered.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td colspan="8" class="py-10 text-ink-muted">No variants match your search or filter.</td>
    `;
    tbody.appendChild(tr);
    return;
  }

  filtered.forEach(r => {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    tr.setAttribute("aria-label", `${r.gene} ${r.id}`);
    tr.onclick = () => openDrawer(r, tr);
    tr.onkeydown = (event) => {
      if (event.target !== tr) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault(); // Space must open the drawer, not scroll the page
        openDrawer(r, tr);
      }
    };

    const tierBadge = r.tier === null
      ? naHtml()
      : `<span class="${TIER_TAG_CLASS}">${escapeHtml(r.tier)}</span>`;
    const categoryBadge = r.category === null
      ? naHtml()
      : `<span class="lds-tag ${categoryTagClass(r)}">${escapeHtml(r.category)}</span>`;

    const acmgPill = r.acmg_actionable
      ? `<span class="lds-tag lds-tag-accent">ACMG</span>`
      : "";
    // The limitation (and any caveats) travel with the row, as a tag with the full text as its tooltip.
    const limitationBadge = r.limitationTooltip === null
      ? ""
      : `<span data-role="limitation" class="lds-tag lds-tag-notice" title="${escapeHtml(r.limitationTooltip)}">${r.limitation === null ? "Caveats" : "Limitation"}</span>`;

    // A composite row (APOE) gives each component's review on its own line, so the column stays narrow.
    const starsLines = r.componentEvidence ? r.componentEvidence.map((p) => `${p.rsid}: ${p.starsText}`) : [r.starsText];
    const guidance = r.statement ?? r.phenotype ?? r.significance;
    const guidanceTitle = [r.statement, r.phenotype, r.limitationTooltip].filter(part => part !== null).join(" ");

    tr.innerHTML = `
      <td class="lds-data font-bold whitespace-nowrap">${escapeHtml(r.id)}</td>
      <td>
        <span class="flex flex-wrap items-center gap-1.5"><span class="font-bold">${escapeHtml(r.gene)}</span> ${acmgPill} ${limitationBadge}</span>
      </td>
      <td class="lds-data font-bold">${valueHtml(r.genotype)}</td>
      <td>${stateTagHtml(r.coverage_state, r.stateLabel)}</td>
      <td>
        <span class="flex flex-wrap items-center gap-1.5">${tierBadge} ${categoryBadge}</span>
      </td>
      <td class="lds-data text-ink-muted whitespace-nowrap">${starsLines.map((line) => `<div>${r.starsMuted ? naHtml(line) : escapeHtml(line)}</div>`).join("")}</td>
      <td class="whitespace-nowrap ${r.magnitude !== null && r.magnitude >= 4 ? 'font-bold text-danger-ink' : ''}">
        ${valueHtml(r.magnitudeShort)} <span class="lds-meta">${r.repute === null ? "" : `(${escapeHtml(r.repute)})`}</span>
      </td>
      <td class="text-ink-muted">
        <div class="min-w-64 max-w-md line-clamp-2" title="${escapeHtml(guidanceTitle)}">${escapeHtml(guidance)}</div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// The element that opened the Inspector; closeDrawer returns focus to it.
let drawerOpener = null;

/**
 * Shows a record in the Inspector (design system Inspector and ui_kits/web/RecordInspector.jsx): docked beside the
 * results, or under them on a narrow screen. It is non-modal: the list stays usable, and opening another record
 * swaps the content. The element ids are the drawer's (#variant-drawer, drawer-*), which the tests read.
 */
function openDrawer(record, opener = document.activeElement) {
  const drawer = document.getElementById("variant-drawer");
  const side = document.getElementById("inspector-side");
  if (!drawer || !side) return;
  const wasOpen = state.selectedVariant !== null;
  state.selectedVariant = record;
  // A map mark is an SVG element; it takes focus back like any HTML opener.
  drawerOpener = (opener instanceof HTMLElement || opener instanceof SVGElement) && opener !== document.body ? opener : null;

  // Header: the KB topic (the gene when it has none), then gene · marker · position, then the result word.
  const gene = state.genes[record.gene];
  document.getElementById("drawer-title").textContent =
    gene && typeof gene.topic === "string" && gene.topic !== "" ? gene.topic : record.gene;
  // The subtitle names the gene once, then the markers ("rs429358 + rs7412" for APOE); the record id stays readable.
  const markerEl = document.getElementById("drawer-rsid");
  markerEl.textContent = record.markerText;
  markerEl.dataset.recordId = record.id;
  document.getElementById("drawer-gene").textContent = record.gene;
  setValue(document.getElementById("drawer-genotype"), record.genotype);
  setValue(document.getElementById("drawer-coord"), record.positionText);
  document.getElementById("drawer-significance").textContent = record.significance;
  setValue(
    document.getElementById("drawer-phenotype"),
    [record.statement, record.phenotype].filter(part => part !== null).join(" ") || null
  );
  setValue(document.getElementById("drawer-stars"), record.starsMuted ? null : record.starsText, record.starsText);
  setValue(document.getElementById("drawer-magnitude"), record.magnitudeText);
  setValue(document.getElementById("drawer-af"), record.afText);

  // Tier and Coverage State badges
  const tierBadgeEl = document.getElementById("drawer-tier-badge");
  const covBadgeEl = document.getElementById("drawer-coverage-state-badge");
  if (tierBadgeEl) {
    setValue(tierBadgeEl, record.tier);
    tierBadgeEl.className = TIER_TAG_CLASS;
  }
  setValue(document.getElementById("drawer-footer-tier"), drawerTierText(record));

  // The result as the design system's StateMark with its word (the shape carries it without colour).
  if (covBadgeEl) covBadgeEl.innerHTML = stateTagInnerHtml(record.coverage_state, record.stateLabel);

  renderLigature(record);
  const figuresShown = renderApoeFigures(record);

  // Limitation (e.g. the star-allele refusal or a single-variant test): from the KB, on every row that has one.
  const refusalBox = document.getElementById("drawer-refusal-box");
  const refusalText = document.getElementById("drawer-refusal-text");
  if (refusalBox && refusalText) {
    if (record.limitation !== null) {
      refusalBox.classList.remove("hidden");
      refusalText.textContent = record.limitation;
    } else {
      refusalBox.classList.add("hidden");
    }
  }

  // Caveats list. An APOE risk figure already shown under the Ligature is not repeated here.
  const caveatsBox = document.getElementById("drawer-caveats-box");
  const caveatsList = document.getElementById("drawer-caveats-list");
  const caveats = record.caveats.filter((c) => !figuresShown.includes(c));
  if (caveatsBox && caveatsList) {
    if (caveats.length > 0) {
      caveatsBox.classList.remove("hidden");
      caveatsList.innerHTML = caveats.map(c => `<li>${escapeHtml(c)}</li>`).join("");
    } else {
      caveatsBox.classList.add("hidden");
      caveatsList.innerHTML = "";
    }
  }

  // ACMG banner
  const acmgBox = document.getElementById("drawer-acmg-box");
  if (record.acmg_actionable) {
    acmgBox.classList.remove("hidden");
  } else {
    acmgBox.classList.add("hidden");
  }

  // CPIC drug response
  const drugBox = document.getElementById("drawer-drug-box");
  const drugText = document.getElementById("drawer-drug-text");
  if (record.drug_response !== null) {
    drugBox.classList.remove("hidden");
    drugText.textContent = record.drug_response;
  } else {
    drugBox.classList.add("hidden");
  }
  document.getElementById("drawer-notices")
    .classList.toggle("hidden", !record.acmg_actionable && record.drug_response === null);

  // ClinVar external links: one per locus whose accession was machine-imported. A composite row (APOE) gets one
  // link per component, labelled with its rsid.
  const clinvarLink = document.getElementById("drawer-clinvar-link");
  clinvarLink.parentElement.querySelectorAll("[data-extra-clinvar-link]").forEach((el) => el.remove());
  if (record.clinvarLinks.length > 0) {
    const labelled = Boolean(record.componentEvidence);
    clinvarLink.classList.remove("hidden");
    let anchor = clinvarLink;
    record.clinvarLinks.forEach((link, i) => {
      if (i > 0) {
        const extra = clinvarLink.cloneNode(false);
        extra.removeAttribute("id");
        extra.setAttribute("data-extra-clinvar-link", "");
        anchor.after(extra);
        anchor = extra;
      }
      anchor.href = link.url;
      anchor.innerHTML = `ClinVar record${labelled ? ` (${escapeHtml(link.rsid)})` : ""}<span class="lds-icon lds-i-arrow-up-right" aria-hidden="true"></span>`;
    });
  } else {
    clinvarLink.classList.add("hidden");
  }

  // Segregation & Recurrence Risk
  renderDrawerSegregation(record);

  // Biotools Multi-Source Insights
  renderDrawerBiotools(record);

  // Human Protein Atlas tissues
  const tissuesContainer = document.getElementById("drawer-hpa-tissues");
  tissuesContainer.innerHTML = "";
  const tissueEntries = Object.entries(record.hpa_tissues);
  if (tissueEntries.length > 0) {
    // The expression level is a word, not a result: one neutral tone.
    tissueEntries.forEach(([tissue, level]) => {
      const div = document.createElement("div");
      div.className = "flex items-center justify-between gap-3 py-1.5 border-b border-line last:border-b-0";
      div.innerHTML = `
        <span class="capitalize text-14">${escapeHtml(tissue)}</span>
        <span class="lds-tag ${NEUTRAL_TAG}">${escapeHtml(level)}</span>
      `;
      tissuesContainer.appendChild(div);
    });
  } else {
    tissuesContainer.innerHTML = `<p class="text-14">${naHtml()}</p>`;
  }

  // Subcellular localization
  const subcellContainer = document.getElementById("drawer-hpa-subcell");
  subcellContainer.innerHTML = "";
  if (record.hpa_subcellular.length > 0) {
    record.hpa_subcellular.forEach(loc => {
      const span = document.createElement("span");
      span.className = `lds-tag ${NEUTRAL_TAG}`;
      span.textContent = loc;
      subcellContainer.appendChild(span);
    });
  } else {
    subcellContainer.innerHTML = `<span class="text-14">${naHtml()}</span>`;
  }

  // Show it and mark its row in the report. Opening focuses the Inspector itself (design system); swapping records
  // while it is docked beside the list leaves focus in the list, where the person is choosing. Under the list (a
  // narrow screen) it is out of sight, so it is brought into view and focused every time.
  side.hidden = false;
  markSelectedFinding(record.id);
  const below = side.offsetTop > side.parentElement.firstElementChild.offsetTop;
  if (!wasOpen || below) drawer.focus({ preventScroll: true });
  if (below) drawer.scrollIntoView({ block: "start" });
}

/**
 * The Ligature (design system components/report/Ligature.jsx): for a genuine two-marker composite (APOE) only, the
 * two markers' genotypes joined into the one result. Every value comes from the record; a missing one says so.
 */
function renderLigature(record) {
  const slot = document.getElementById("drawer-ligature");
  const parts = record.components ?? [];
  slot.hidden = parts.length !== 2;
  if (parts.length !== 2) {
    slot.replaceChildren();
    return;
  }
  const marker = (c) => `<span>${escapeHtml(c.rsid)} ${valueHtml(c.genotype_display ?? null)}</span>`;
  const result = record.diplotypeDisplay === null
    ? naHtml()
    : `${escapeHtml(record.gene)} ${escapeHtml(record.diplotypeDisplay)}`;
  slot.innerHTML = `
    <figure class="lds-ligature">
      <svg viewBox="0 0 240 34" width="240" height="34" aria-hidden="true" focusable="false">
        <path class="lds-ligature-arch" d="M30 32 C 30 4, 210 4, 210 32"/>
        <circle class="lds-ligature-dot" cx="120" cy="11" r="4"/>
      </svg>
      <div class="lds-ligature-markers">${parts.map(marker).join("")}</div>
      <div class="lds-ligature-result">${result}</div>
      <figcaption class="lds-ligature-caption">One result built from two markers</figcaption>
    </figure>`;
}

/**
 * APOE only: the risk ratio and the estimated lifetime risk under the Ligature, as the knowledge base states them and
 * each with its curation label (view-model.js apoeCardModel; whether to cite or remove them is the owner's decision).
 * With no diplotype there is no figure, and each says "Not available". Returns the caveat lines the figures came from,
 * so the caveats list does not repeat them.
 */
function renderApoeFigures(record) {
  const slot = document.getElementById("drawer-apoe-figures");
  const isApoe = state.apoe !== null && record.id === state.apoe.id;
  slot.hidden = !isApoe;
  if (!isApoe) return [];
  const model = apoeCardModel(record);
  const riskRatio = model.resolved ? model.riskBadge : null;
  setValue(document.getElementById("drawer-apoe-risk-ratio"), riskRatio);
  setValue(document.getElementById("drawer-apoe-lifetime"), model.lifetime);
  // Each figure is its caveat line after the line's "<label>: " prefix.
  return [riskRatio, model.lifetime]
    .filter((figure) => figure !== null)
    .map((figure) => record.caveats.find((c) => c.endsWith(`: ${figure}`)))
    .filter((line) => line !== undefined);
}

function renderDrawerSegregation(record) {
  // No segregation inputs exist for a locus with no interpretable genotype (not tested, no-call).
  const seg = record.segregation ?? null;
  const modeBadge = document.getElementById("drawer-seg-mode-badge");
  const priorEl = document.getElementById("drawer-seg-carrier-prior");
  const penetranceEl = document.getElementById("drawer-seg-penetrance");
  const riskUnscreenedEl = document.getElementById("drawer-seg-risk-unscreened");
  const riskCarrierEl = document.getElementById("drawer-seg-risk-carrier");
  const container = document.getElementById("drawer-segregation-container");
  const header = container ? container.querySelector("[data-role='seg-title']") : null;
  const simTitle = container ? container.querySelector("#drawer-partner-buttons").previousElementSibling : null;
  const mendelian = Boolean(seg && seg.mendelian_disease);
  const recessive = Boolean(seg && seg.model === "autosomal_recessive");

  // Wording follows the gene's inheritance model: disease and recurrence language is for Mendelian genes only.
  // For a recessive gene the headline figure is the genotype probability (two copies), before any penetrance.
  setLabel(header, mendelian ? null : "Passing it on");
  // The other person is "the other parent" (design system), and the reader's own file is "your genotype".
  setLabel(header && header.nextElementSibling, mendelian ? null : "The chance a child inherits the variant, from your genotype.");
  setLabel(priorEl.previousElementSibling, mendelian ? null : "Allele frequency (gnomAD)");
  setLabel(
    riskUnscreenedEl.previousElementSibling,
    !mendelian
      ? "Child inherits, if the other parent is unscreened"
      : recessive ? "Risk if the other parent is unscreened (genotype probability)" : null
  );
  setLabel(
    riskCarrierEl.previousElementSibling,
    !mendelian
      ? "Child inherits, if the other parent has no variant"
      : recessive ? "Risk if the other parent is a carrier (genotype probability)" : null
  );
  setLabel(simTitle && simTitle.firstElementChild, mendelian ? null : "Offspring allele simulator");
  setLabel(simTitle && simTitle.lastElementChild, "Other parent");
  document.querySelectorAll(".partner-sim-btn").forEach(b => {
    setLabel(b, mendelian ? null : SIM_BUTTON_LABELS[b.getAttribute("data-partner")]);
  });

  if (!seg) {
    setValue(modeBadge, null);
    setValue(priorEl, null);
    setValue(penetranceEl, null);
    setValue(riskUnscreenedEl, null);
    setValue(riskCarrierEl, null);
    document.querySelectorAll(".partner-sim-btn").forEach(btn => { btn.onclick = null; });
    renderSimulator(null, null);
    renderPartnerNote(null, null);
    return;
  }

  const outcomeFor = (partner) => geneOutcome(state.genes[seg.gene], offspringDistribution(seg.altCount, partner, seg.af), seg.allele);
  const headline = (out) => (!out.available ? null : fmtPct(mendelian ? out.affected : out.inherits_allele));

  // The inheritance model is a label, not a result: one neutral tone.
  if (modeBadge) modeBadge.textContent = MODEL_LABELS[seg.model] ?? seg.model;

  if (seg.af === null) {
    setValue(priorEl, null);
  } else if (mendelian) {
    const prior = seg.carrierPrior;
    setValue(priorEl, prior ? `1 in ${prior.oneIn} (${fmtPct(prior.frequency)})` : null);
  } else {
    priorEl.textContent = fmtPct(seg.af);
  }
  if (penetranceEl) {
    if (!mendelian) penetranceEl.textContent = "Not applicable";
    else setValue(penetranceEl, seg.penetrance === null ? null : fmtPct(seg.penetrance));
  }
  if (riskUnscreenedEl) setValue(riskUnscreenedEl, headline(outcomeFor("unscreened")));
  if (riskCarrierEl) setValue(riskCarrierEl, headline(outcomeFor(mendelian ? "heterozygous" : "wildtype")));

  // Setup simulator partner buttons
  const buttons = document.querySelectorAll(".partner-sim-btn");
  const setActive = (active) => buttons.forEach(b => {
    b.setAttribute("aria-pressed", String(b === active));
  });
  buttons.forEach(btn => {
    btn.onclick = () => {
      setActive(btn);
      updateSimulator(btn.getAttribute("data-partner"), record);
    };
  });

  // Reset to unscreened active button
  setActive([...buttons].find(b => b.getAttribute("data-partner") === "unscreened"));
  updateSimulator("unscreened", record);
}

// The buttons keep their data-partner keys; each maps to a partner genotype model.
const SIM_PARTNER_MODEL = { unscreened: "unscreened", carrier: "heterozygous", affected: "homozygous", wildtype: "wildtype" };
// The other parent's options in the design system's words (RecordInspector.jsx): Mendelian genes keep the markup's
// Unscreened, Carrier, Affected, No variant; the others say how many copies the other parent has.
const SIM_BUTTON_LABELS = { unscreened: "Unscreened", carrier: "One copy", affected: "Two copies", wildtype: "No variant" };

/** Sets an element's text, remembering the original so a later null restores it. */
function setLabel(el, text) {
  if (!el) return;
  if (el.dataset.origText === undefined) el.dataset.origText = el.textContent;
  el.textContent = text === null ? el.dataset.origText : text;
}

/** Says in words which partner model produced the figures on screen. */
function renderPartnerNote(partnerKey, seg) {
  const note = document.getElementById("drawer-partner-model-note");
  if (!note) return;
  note.textContent = seg ? partnerModelNote(SIM_PARTNER_MODEL[partnerKey], seg.af) : "";
}

function updateSimulator(partnerKey, record) {
  const seg = record.segregation;
  const dist = offspringDistribution(seg.altCount, SIM_PARTNER_MODEL[partnerKey], seg.af);
  renderSimulator(geneOutcome(state.genes[seg.gene], dist, seg.allele), seg);
  renderPartnerNote(partnerKey, seg);
}

/** Three probability rows and the effective-penetrance line; a null outcome (no genotype) shows "Not available". */
function renderSimulator(out, seg) {
  const rows = [
    { id: "affected", label: "Affected probability", value: null },
    { id: "carrier", label: "Carrier probability", value: null },
    { id: "wildtype", label: "Wild-type (non-carrier)", value: null }
  ];
  let effective = null;
  let effectiveLabel = "Effective penetrance, adjusted";
  let reason = "";
  if (out && !out.available) {
    reason = out.reason;
  } else if (out && out.kind === "transmission") {
    rows[0] = { id: "affected", label: out.label, value: out.inherits_allele };
    rows[1] = { id: "carrier", label: "Inherits one copy", value: out.one_copy };
    rows[2] = { id: "wildtype", label: "Inherits no copy", value: out.none };
    effective = "Not applicable";
    effectiveLabel = "Clinical penetrance";
  } else if (out && seg.model === "autosomal_recessive") {
    // Two different "affected" figures: the genotype probability (two copies), and that probability times the stated penetrance.
    rows[0] = { id: "affected", label: "Affected genotype probability (two copies)", value: out.affected };
    rows[1].value = out.carrier;
    rows[2].value = out.p0;
    effectiveLabel = "Affected probability, adjusted for stated penetrance";
    const adjusted = penetranceAdjustedAffected(out, seg.penetrance);
    effective = adjusted === null ? null : fmtPct(adjusted);
  } else if (out) {
    rows[0] = { id: "affected", label: "Affected probability (penetrance-adjusted)", value: out.affected };
    rows[1] = { id: "carrier", label: "Inherits one copy", value: out.p1 };
    rows[2] = { id: "wildtype", label: "Does not inherit", value: out.p0 };
    effective = fmtPct(out.affected);
  }
  for (const row of rows) {
    const valueEl = document.getElementById(`sim-p-${row.id}`);
    const barEl = document.getElementById(`sim-bar-${row.id}`);
    setLabel(valueEl && valueEl.previousElementSibling, out ? row.label : null);
    if (valueEl) {
      setValue(valueEl, row.value === null ? null : fmtPct(row.value));
      valueEl.title = reason;
    }
    if (barEl) barEl.style.width = row.value === null ? "0%" : `${Math.min(100, Math.max(0, row.value * 100))}%`;
  }
  const effEl = document.getElementById("sim-effective-risk");
  if (effEl) {
    setLabel(effEl.previousElementSibling, effectiveLabel);
    setValue(effEl, effective);
  }
}

function renderDrawerBiotools(record) {
  const b = record.biotools;
  const geneBadge = document.getElementById("drawer-biotool-gene-badge");
  if (geneBadge) geneBadge.textContent = record.gene;

  // AlphaFold
  setValue(document.getElementById("drawer-af-uniprot"), b.uniprot);

  // The pLDDT score is shown as its number in the neutral tone; the number carries the meaning.
  setValue(document.getElementById("drawer-af-plddt"), b.plddt === null ? null : b.plddt.toFixed(1));

  setValue(document.getElementById("drawer-af-status"), b.status);

  const domainsEl = document.getElementById("drawer-af-domains");
  if (domainsEl) {
    domainsEl.innerHTML = "";
    if (b.domains.length > 0) {
      b.domains.forEach(d => {
        const div = document.createElement("div");
        div.textContent = d;
        domainsEl.appendChild(div);
      });
    } else {
      domainsEl.innerHTML = `<div>${naHtml()}</div>`;
    }
  }

  setValue(document.getElementById("drawer-af-joints"), b.joints);

  // Ensembl VEP
  setValue(document.getElementById("drawer-ens-transcript"), b.transcript);
  setValue(document.getElementById("drawer-ens-alphamissense"), b.alphamissense);
  setValue(document.getElementById("drawer-ens-loeuf"), b.constraint);

  // ENCODE cCREs
  const encodeEl = document.getElementById("drawer-encode-tissues");
  if (encodeEl) {
    encodeEl.innerHTML = "";
    if (b.tissues.length === 0) {
      encodeEl.innerHTML = `<div class="text-14">${naHtml()}</div>`;
      return;
    }
    // The bars are scaled to the largest value, with a floor of 100 TPM so a small value does not fill the bar.
    const maxTpm = Math.max(...b.tissues.map(([, tpm]) => tpm), 100);

    b.tissues.forEach(([tissue, tpm]) => {
      const pct = Math.round((tpm / maxTpm) * 100);
      const row = document.createElement("div");
      row.className = "lds-prob";
      row.innerHTML = `
        <div class="lds-prob-head">
          <span class="capitalize">${escapeHtml(tissue)}</span>
          <span>${escapeHtml(tpm.toLocaleString())} TPM</span>
        </div>
        <div class="lds-prob-track lds-prob-track-thin">
          <div class="lds-prob-bar" style="width: ${pct}%"></div>
        </div>
      `;
      encodeEl.appendChild(row);
    });
  }
}

function closeDrawer() {
  const drawer = document.getElementById("variant-drawer");
  const side = document.getElementById("inspector-side");
  const focusWasInside = Boolean(drawer && drawer.contains(document.activeElement));
  if (side) side.hidden = true;
  state.selectedVariant = null;
  markSelectedFinding(null);
  // Focus that was in the Inspector goes back to whatever opened it (a table row, or a button), if it is still on
  // the page. Focus the person moved elsewhere stays where it is.
  const lost = focusWasInside || document.activeElement === null || document.activeElement === document.body;
  if (lost && drawerOpener && drawerOpener.isConnected) drawerOpener.focus();
  drawerOpener = null;
}

/** Every row the file produced, once each: observed findings first, then wild-type, gaps and insufficient evidence. */
function allRows() {
  const seen = new Set();
  return listedRows().filter((vm) => !seen.has(vm.id) && seen.add(vm.id));
}

function exportMarkdownReport() {
  if (!state.qc) return;
  const md = markdownReport({
    fileName: state.fileName,
    qc: state.qc,
    manifest: state.manifest,
    coverage: state.coverageSummary,
    apoe: state.apoe,
    compoundHeterozygotes: state.compoundHeterozygotes,
    independentAssortment: state.independentAssortment,
    records: state.records,
    negativeChecks: state.negativeChecks,
    arrayGaps: state.arrayGaps,
    insufficientEvidence: state.insufficientEvidence
  });
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  downloadBlob(blob, `Lucidase_Report_${Date.now()}.md`);
}

function exportCsvReport() {
  if (!state.qc) return;
  const blob = new Blob([csvReport(allRows(), state.genes)], { type: "text/csv;charset=utf-8" });
  downloadBlob(blob, `Lucidase_Variants_${Date.now()}.csv`);
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
