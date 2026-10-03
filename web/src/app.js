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
import {
  NOT_AVAILABLE,
  acmgVersionLabel,
  apoeCardModel,
  csvReport,
  drawerTierText,
  escapeHtml,
  fmtPct,
  formatRate,
  heroScopeText,
  kbBadge,
  markdownReport,
  partnerModelNote,
  testedVariantCounts,
  toViewModel,
  MODEL_LABELS,
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
  selectedVariant: null,
  filterCategory: "all",
  searchQuery: "",
  sortBy: "magnitude",
  // Not a clinical field: a missing or unreadable stored preference means the light theme.
  theme: readStoredTheme()
};

// localStorage throws when site data is blocked; the theme is not a clinical field, so that means light.
function readStoredTheme() {
  try {
    return localStorage.getItem("lucidase-theme") || "light";
  } catch {
    return "light";
  }
}

// Initialize Application (handles both pre- and post-DOMContentLoaded module execution)
function initApp() {
  console.log("initApp executed, readyState:", document.readyState);
  initTheme();
  initEventListeners();
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

function initTheme() {
  setTheme(state.theme);
  const btnToggle = document.getElementById("btn-theme-toggle");
  if (btnToggle) {
    btnToggle.addEventListener("click", () => {
      const nextTheme = state.theme === "light" ? "dark" : "light";
      setTheme(nextTheme);
    });
  }
}

function setTheme(theme) {
  state.theme = theme;
  try {
    localStorage.setItem("lucidase-theme", theme);
  } catch {
    // Blocked or full storage: the theme still applies for this session.
  }
  document.documentElement.setAttribute("data-theme", theme);

  const icon = document.getElementById("theme-toggle-icon");
  const text = document.getElementById("theme-toggle-text");
  if (icon && text) {
    if (theme === "dark") {
      icon.textContent = "☀️";
      text.textContent = "Light Mode";
    } else {
      icon.textContent = "🌙";
      text.textContent = "Dark HUD";
    }
  }
}

// A value the record or the KB does not carry is shown as "Not available" in a muted style, never as a placeholder.
const MUTED = "text-slate-500 dark:text-slate-400 italic";
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
      updateProgress(data.percent, data.status);
    } else if (data.type === "complete") {
      stopWorker();
      try {
        handleParseComplete(data);
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
  document.getElementById("progress-section").classList.add("hidden");
  document.getElementById("results-section").classList.add("hidden");
  const box = document.getElementById("analysis-error");
  document.getElementById("analysis-error-detail").textContent =
    String(message || "unknown error");
  box.classList.remove("hidden");
  setInputsDisabled(false);
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
  const btnInspectApoe = document.getElementById("btn-inspect-apoe");

  // Drag and drop
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("border-sky-500", "bg-sky-500/10");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("border-sky-500", "bg-sky-500/10");
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("border-sky-500", "bg-sky-500/10");
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
        updateProgress(10, "Fetching demo 23andMe profile...");
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

  // Search input
  searchInput.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    renderVariantsTable();
  });

  // Filter tabs
  filterButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      filterButtons.forEach(b => {
        b.classList.remove("tab-active", "bg-sky-600", "text-white", "dark:bg-sky-500/20", "dark:text-sky-300", "border-sky-600", "dark:border-sky-400");
        b.classList.add("text-slate-600", "dark:text-slate-400");
      });
      btn.classList.add("tab-active", "bg-sky-600", "text-white", "dark:bg-sky-500/20", "dark:text-sky-300", "border-sky-600", "dark:border-sky-400");
      btn.classList.remove("text-slate-600", "dark:text-slate-400");
      state.filterCategory = btn.getAttribute("data-filter");
      renderVariantsTable();
    });
  });

  // Exports
  btnExportMd.addEventListener("click", exportMarkdownReport);
  btnExportCsv.addEventListener("click", exportCsvReport);


  // Detail drawer close
  if (btnCloseDrawer) {
    btnCloseDrawer.addEventListener("click", closeDrawer);
  }

  // Inspect APOE button
  if (btnInspectApoe) {
    btnInspectApoe.addEventListener("click", () => {
      const apoeRec = state.apoe;
      if (apoeRec) {
        openDrawer(apoeRec);
      }
    });
  }
}

function handleFileSelected(file) {
  state.fileName = file.name;
  updateProgress(5, `Reading ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)...`);

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
    document.getElementById("analysis-error").classList.add("hidden");
    setInputsDisabled(true);
    document.getElementById("progress-section").classList.remove("hidden");
    document.getElementById("results-section").classList.add("hidden");
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
  if (bar) bar.style.width = `${percent}%`;
  if (msg) msg.textContent = message;
  if (pct) pct.textContent = `${percent}%`;
}

function handleParseComplete(data) {
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

  document.getElementById("progress-section").classList.add("hidden");
  document.getElementById("analysis-error").classList.add("hidden");
  document.getElementById("results-section").classList.remove("hidden");
  setInputsDisabled(false);

  renderKbClaims(state.manifest);
  renderQC();
  renderSummaryCards();
  renderApoeCard();
  renderAssortmentSection();
  renderVariantsTable();
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
  sexBadge.className = "inline-flex items-center px-3 py-1 rounded-sm text-xs font-semibold bg-slate-200 dark:bg-slate-500/20 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-500/30";
}

/** Every card shows the worker's own figure: the category cards and the coverage cards are not recounted here. */
function renderSummaryCards() {
  const sum = state.summary;
  const cov = state.coverageSummary;
  if (!sum || !cov) return;
  const figure = (value) => (typeof value === "number" ? value.toLocaleString() : NOT_AVAILABLE);
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = figure(value);
  };

  set("count-pathogenic", sum.pathogenic_count);
  set("count-carrier", sum.carrier_count);
  set("count-pgx", sum.pgx_count);
  set("count-risk", sum.risk_factor_count);
  set("count-acmg", sum.acmg_actionable_findings);

  set("count-state-observed", cov.supported_and_observed_count);
  set("count-state-negative", cov.supported_not_observed_count);
  set("count-state-gaps", cov.not_tested_by_array_count);
  set("count-state-outside", cov.outside_coverage_count);
  set("count-state-insufficient", cov.insufficient_evidence_count);
}

const APOE_ACCENTS = {
  e4e4: { border: "border-rose-500", badge: "badge-pathogenic" },
  e4: { border: "border-amber-500", badge: "badge-carrier" },
  e2: { border: "border-purple-500", badge: "badge-pgx" },
  e3e3: { border: "border-emerald-500", badge: "badge-benign" }
};
const APOE_NEUTRAL_BADGE = "bg-slate-200 dark:bg-slate-500/20 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-500/30";

function renderApoeCard() {
  const card = document.getElementById("apoe-status-card");
  if (!card) return;

  if (!state.apoe) {
    card.classList.add("hidden");
    return;
  }

  card.classList.remove("hidden");
  const model = apoeCardModel(state.apoe);

  const titleEl = document.getElementById("apoe-diplotype-title");
  const riskRatioEl = document.getElementById("apoe-risk-ratio");
  const descEl = document.getElementById("apoe-phenotype-desc");
  const rawLociEl = document.getElementById("apoe-raw-loci");
  const lifetimeEl = document.getElementById("apoe-lifetime-stat");
  const pillEl = document.getElementById("apoe-carrier-pill");
  const hpaEl = document.getElementById("apoe-hpa-desc");

  // Everything below is KB text; an unresolved APOE shows the reason and no numbers.
  titleEl.textContent = model.title;
  rawLociEl.textContent = model.rawLoci;
  setValue(descEl, model.description);
  setValue(riskRatioEl, model.riskBadge);
  setValue(lifetimeEl, model.lifetime);
  pillEl.textContent = model.pill;
  setValue(hpaEl, model.hpaSummary);

  // Visual accents depending on risk profile (existing classes only)
  const accent = APOE_ACCENTS[model.accent] ?? null;

  if (accent) {
    card.className = `glass-panel p-6 border-l-4 ${accent.border} transition-all duration-200 bg-white dark:bg-slate-900/60`;
    riskRatioEl.className = `px-2.5 py-1 text-xs font-bold rounded-sm font-mono border ${accent.badge}`;
    pillEl.className = `px-2 py-0.5 text-[11px] font-bold uppercase rounded-sm border ${accent.badge}`;
  } else {
    // No diplotype asserted: neutral accents, never the normal-baseline green.
    card.className = "glass-panel p-6 border-l-4 transition-all duration-200 bg-white dark:bg-slate-900/60 border-slate-300 dark:border-slate-700";
    riskRatioEl.className = `px-2.5 py-1 text-xs font-bold rounded-sm font-mono ${APOE_NEUTRAL_BADGE}`;
    pillEl.className = `px-2 py-0.5 text-[11px] font-bold uppercase rounded-sm ${APOE_NEUTRAL_BADGE}`;
  }
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
    badge.textContent = `${totalFindings} Multi-Locus Finding${totalFindings === 1 ? '' : 's'}`;
  }
  container.innerHTML = "";

  // Render Compound Heterozygotes (e.g. HFE C282Y / H63D). Every interpolated value is escaped.
  compounds.forEach(ch => {
    const card = document.createElement("div");
    card.className = "p-4 rounded-sm bg-slate-50 dark:bg-slate-900/50 border border-indigo-200 dark:border-indigo-900/60 space-y-3";
    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="text-xs uppercase font-bold tracking-wider text-indigo-700 dark:text-indigo-400 font-mono">Possible Compound Heterozygote · Phase Unknown</span>
          <span class="px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border badge-pathogenic">${escapeHtml(ch.significance)}</span>
        </div>
        <span class="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">${escapeHtml(ch.gene)}</span>
      </div>
      <div>
        <h4 class="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono">${escapeHtml(ch.title)}</h4>
        <p class="text-xs text-slate-600 dark:text-slate-400 font-serif mt-1">${escapeHtml(ch.summary)}</p>
      </div>
      <div class="p-2.5 rounded-sm bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800/40 text-[11px] font-mono text-indigo-900 dark:text-indigo-300">
        ⚖️ <strong>Segregation:</strong> ${escapeHtml(ch.segregation_notes)}
      </div>
      <div class="flex justify-end pt-1">
        <button type="button" class="btn btn-xs btn-outline border-indigo-400 dark:border-indigo-600 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-500/10 rounded-sm font-mono text-[11px] btn-inspect-gene" data-gene="${escapeHtml(ch.gene)}">
          🔬 Inspect ${escapeHtml(ch.gene)} Locus ↗
        </button>
      </div>
    `;
    container.appendChild(card);
  });

  // Render co-occurring variant alleles on unlinked loci (e.g. F5 Chr 1 + F2 Chr 11)
  assortments.forEach(ia => {
    const card = document.createElement("div");
    card.className = "p-4 rounded-sm bg-slate-50 dark:bg-slate-900/50 border border-amber-200 dark:border-amber-900/60 space-y-3";
    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="text-xs uppercase font-bold tracking-wider text-amber-700 dark:text-amber-400 font-mono">Co-occurring Variant Alleles</span>
          <span class="px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border badge-risk">Multi-Locus</span>
        </div>
        <span class="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">${escapeHtml(ia.genes.join(" + "))}</span>
      </div>
      <div>
        <h4 class="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono">${escapeHtml(ia.type)}</h4>
        <p class="text-xs text-slate-600 dark:text-slate-400 font-serif mt-1">${escapeHtml(ia.description)}</p>
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs font-mono">
        <div class="p-2 rounded-sm bg-white dark:bg-slate-950 border border-amber-200 dark:border-amber-800/40">
          <span class="text-[9px] uppercase text-slate-400 block">Loci on Different Chromosomes</span>
          <span class="font-bold text-slate-800 dark:text-slate-200 mt-0.5 block">${escapeHtml(ia.loci.join(" · "))}</span>
        </div>
        <div class="p-2 rounded-sm bg-white dark:bg-slate-950 border border-amber-200 dark:border-amber-800/40">
          <span class="text-[9px] uppercase text-slate-400 block">Child Inherits All Listed Alleles</span>
          <span class="font-bold text-amber-600 dark:text-amber-400 mt-0.5 block" title="${escapeHtml(ia.assumption)}">${Math.round(ia.joint_transmission_prob * 100)}%</span>
        </div>
      </div>
      <div class="flex justify-end space-x-2 pt-1">
        ${ia.genes.map(g => `
          <button type="button" class="btn btn-xs btn-outline border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-amber-500 rounded-sm font-mono text-[11px] btn-inspect-gene" data-gene="${escapeHtml(g)}">
            Inspect ${escapeHtml(g)} ↗
          </button>
        `).join("")}
      </div>
    `;
    container.appendChild(card);
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

const STATE_BADGE_CLASS = {
  supported_and_observed: "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30",
  supported_not_observed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/30",
  not_tested_by_array: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30",
  insufficient_evidence: "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300 border border-rose-300 dark:border-rose-500/30"
};

// The one neutral (slate) look: any category, tier or composite label the page has no explicit style for.
const NEUTRAL_BADGE_COLOURS = "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300 border-slate-300 dark:border-slate-700";

// Categories with an explicit style. A Carrier flag on the row also gets the carrier style. Everything else
// (Trait, Not detected, a category added later) is neutral, never the benign (green) look.
const CATEGORY_BADGE_CLASS = {
  Pathogenic: "badge-pathogenic",
  Carrier: "badge-carrier",
  Pharmacogenomics: "badge-pgx",
  "Risk Factor": "badge-risk"
};
const categoryBadgeClass = (r) =>
  CATEGORY_BADGE_CLASS[r.category] ?? (r.isCarrier ? CATEGORY_BADGE_CLASS.Carrier : `border ${NEUTRAL_BADGE_COLOURS}`);

const TIER_BADGE_CLASS = {
  "Tier A": "bg-sky-100 text-sky-800 border border-sky-300 dark:bg-sky-900/40 dark:text-sky-300 dark:border-sky-700",
  "Tier B": "bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-700",
  "Tier C": "bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700",
  "Tier D": "bg-slate-100 text-slate-700 border border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700"
};

function renderVariantsTable() {
  const tbody = document.getElementById("variants-tbody");
  tbody.innerHTML = "";

  let dataset = state.records;
  if (state.filterCategory === "negative") {
    dataset = state.negativeChecks;
  } else if (state.filterCategory === "gaps") {
    dataset = state.arrayGaps;
  } else if (state.filterCategory === "insufficient") {
    dataset = state.insufficientEvidence;
  }

  const filtered = dataset.filter(r => {
    // Category filter for subcategories of observed findings
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

  let countLabel = `Showing ${filtered.length} of ${state.records.length} clinical findings`;
  if (state.filterCategory === "negative") {
    countLabel = `Showing ${filtered.length} loci tested wild-type (supported but not observed)`;
  } else if (state.filterCategory === "gaps") {
    countLabel = `Showing ${filtered.length} loci not genotyped on this chip (array gaps)`;
  } else if (state.filterCategory === "insufficient") {
    countLabel = `Showing ${filtered.length} loci with conflicting / insufficient evidence (State 5)`;
  }
  document.getElementById("showing-count").textContent = countLabel;

  if (filtered.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td colspan="8" class="py-12 text-center text-slate-500 dark:text-slate-400">
        <div class="inline-block p-4 rounded-sm bg-slate-100 dark:bg-slate-800 mb-2">🔍</div>
        <p class="font-medium">No variants match your search or filter.</p>
      </td>
    `;
    tbody.appendChild(tr);
    return;
  }

  filtered.forEach(r => {
    const tr = document.createElement("tr");
    tr.className = "cursor-pointer border-b border-slate-200 dark:border-slate-800/60 transition-colors hover:bg-slate-50/80 dark:hover:bg-slate-800/40";
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

    const categoryClass = categoryBadgeClass(r);

    const stateBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold ${STATE_BADGE_CLASS[r.coverage_state]}">${escapeHtml(r.stateBadge)}</span>`;
    const tierBadge = r.tier === null
      ? `<span class="mr-1.5">${naHtml()}</span>`
      : `<span class="px-1.5 py-0.5 rounded-sm text-[10px] font-bold uppercase font-mono ${TIER_BADGE_CLASS[r.tier] ?? `border ${NEUTRAL_BADGE_COLOURS}`} mr-1.5">${escapeHtml(r.tier)}</span>`;
    const categoryBadge = r.category === null
      ? naHtml()
      : `<span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold ${categoryClass}">${escapeHtml(r.category)}</span>`;

    const acmgPill = r.acmg_actionable
      ? `<span class="ml-1.5 px-1.5 py-0.5 text-[10px] uppercase font-bold rounded-sm bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30">ACMG</span>`
      : "";
    // The limitation (and any caveats) travel with the row, as a badge with the full text as its tooltip.
    const limitationBadge = r.limitationTooltip === null
      ? ""
      : `<span data-role="limitation" class="ml-1.5 px-1.5 py-0.5 text-[10px] uppercase font-bold rounded-sm bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30" title="${escapeHtml(r.limitationTooltip)}">${r.limitation === null ? "Caveats" : "Limitation"}</span>`;

    const guidance = r.statement ?? r.phenotype ?? r.significance;
    const guidanceTitle = [r.statement, r.phenotype, r.limitationTooltip].filter(part => part !== null).join(" ");

    tr.innerHTML = `
      <td class="py-3 px-4 font-mono font-bold text-sky-700 dark:text-sky-400">${escapeHtml(r.id)}</td>
      <td class="py-3 px-4 font-semibold text-slate-900 dark:text-slate-100">
        ${escapeHtml(r.gene)} ${acmgPill} ${limitationBadge}
      </td>
      <td class="py-3 px-4 font-mono font-bold text-slate-900 dark:text-slate-100">${valueHtml(r.genotype)}</td>
      <td class="py-3 px-4">${stateBadge}</td>
      <td class="py-3 px-4 flex items-center">
        ${tierBadge}
        ${categoryBadge}
      </td>
      <td class="py-3 px-4 text-amber-500 text-xs font-mono tracking-wider">${r.starsMuted ? naHtml(r.starsText) : escapeHtml(r.starsText)}</td>
      <td class="py-3 px-4 font-semibold text-xs ${r.magnitude !== null && r.magnitude >= 4 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-700 dark:text-slate-300'}">
        ${valueHtml(r.magnitudeShort)} <span class="text-[10px] text-slate-400">${r.repute === null ? "" : `(${escapeHtml(r.repute)})`}</span>
      </td>
      <td class="py-3 px-4 text-xs text-slate-700 dark:text-slate-300 max-w-md truncate" title="${escapeHtml(guidanceTitle)}">
        ${escapeHtml(guidance)}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

const TIER_DRAWER_CLASS = {
  "Tier A": "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300 border-sky-300 dark:border-sky-500/30",
  "Tier B": "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30",
  "Tier C": "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border-amber-300 dark:border-amber-500/30"
};
const TIER_DRAWER_NEUTRAL = `px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono ${NEUTRAL_BADGE_COLOURS}`;

const COVERAGE_DRAWER_CLASS = {
  supported_and_observed: "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300 border-sky-300 dark:border-sky-500/30",
  supported_not_observed: "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30",
  not_tested_by_array: "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border-amber-300 dark:border-amber-500/30",
  insufficient_evidence: "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300 border-rose-300 dark:border-rose-500/30"
};

// The element that opened the drawer; closeDrawer returns focus to it.
let drawerOpener = null;

function openDrawer(record, opener = document.activeElement) {
  state.selectedVariant = record;
  drawerOpener = opener instanceof HTMLElement && opener !== document.body ? opener : null;
  const drawer = document.getElementById("variant-drawer");
  if (!drawer) return;

  document.getElementById("drawer-rsid").textContent = record.id;
  document.getElementById("drawer-gene").textContent = record.gene;
  setValue(document.getElementById("drawer-genotype"), record.genotype);
  setValue(document.getElementById("drawer-coord"), record.positionText);
  document.getElementById("drawer-significance").textContent = record.significance;
  setValue(
    document.getElementById("drawer-phenotype"),
    [record.statement, record.phenotype].filter(part => part !== null).join(" ") || null
  );
  setValue(document.getElementById("drawer-stars"), record.starsMuted ? null : record.starsDetail, record.starsText);
  setValue(document.getElementById("drawer-magnitude"), record.magnitudeText);
  setValue(document.getElementById("drawer-af"), record.afText);

  // Tier and Coverage State badges
  const tierBadgeEl = document.getElementById("drawer-tier-badge");
  const covBadgeEl = document.getElementById("drawer-coverage-state-badge");
  if (tierBadgeEl) {
    setValue(tierBadgeEl, record.tier);
    tierBadgeEl.className = TIER_DRAWER_CLASS[record.tier] ?? TIER_DRAWER_NEUTRAL;
  }
  setValue(document.getElementById("drawer-footer-tier"), drawerTierText(record));

  if (covBadgeEl) {
    covBadgeEl.textContent = record.stateLabel;
    covBadgeEl.className = COVERAGE_DRAWER_CLASS[record.coverage_state];
  }

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

  // Caveats list
  const caveatsBox = document.getElementById("drawer-caveats-box");
  const caveatsList = document.getElementById("drawer-caveats-list");
  if (caveatsBox && caveatsList) {
    if (record.caveats.length > 0) {
      caveatsBox.classList.remove("hidden");
      caveatsList.innerHTML = record.caveats.map(c => `<li>${escapeHtml(c)}</li>`).join("");
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
      anchor.textContent = `Open ClinVar Record${labelled ? ` (${link.rsid})` : ""} ↗`;
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
    tissueEntries.forEach(([tissue, level]) => {
      let colorClass = "bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300 border-sky-300 dark:border-sky-500/30";
      if (level === "High") colorClass = "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30";
      else if (level === "Medium") colorClass = "bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-500/30";

      const div = document.createElement("div");
      div.className = "flex items-center justify-between p-2 rounded-sm bg-slate-100 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/50 text-xs";
      div.innerHTML = `
        <span class="capitalize text-slate-800 dark:text-slate-200 font-medium">${escapeHtml(tissue)}</span>
        <span class="px-2 py-0.5 rounded-sm text-[11px] font-semibold border ${colorClass}">${escapeHtml(level)}</span>
      `;
      tissuesContainer.appendChild(div);
    });
  } else {
    tissuesContainer.innerHTML = `<p class="text-xs">${naHtml()}</p>`;
  }

  // Subcellular localization
  const subcellContainer = document.getElementById("drawer-hpa-subcell");
  subcellContainer.innerHTML = "";
  if (record.hpa_subcellular.length > 0) {
    record.hpa_subcellular.forEach(loc => {
      const span = document.createElement("span");
      span.className = "px-2.5 py-1 rounded-sm text-xs font-medium bg-purple-100 dark:bg-purple-500/15 text-purple-800 dark:text-purple-300 border border-purple-300 dark:border-purple-500/30 font-mono";
      span.textContent = loc;
      subcellContainer.appendChild(span);
    });
  } else {
    subcellContainer.innerHTML = `<span class="text-xs">${naHtml()}</span>`;
  }

  // Show drawer
  drawer.classList.remove("translate-x-full");
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
  const header = container ? container.querySelector("span.tracking-wider") : null;
  const simTitle = container ? container.querySelector("#drawer-partner-buttons").previousElementSibling : null;
  const mendelian = Boolean(seg && seg.mendelian_disease);
  const recessive = Boolean(seg && seg.model === "autosomal_recessive");

  // Wording follows the gene's inheritance model: disease and recurrence language is for Mendelian genes only.
  // For a recessive gene the headline figure is the genotype probability (two copies), before any penetrance.
  setLabel(header, mendelian ? null : "Allele Transmission");
  setLabel(header && header.nextElementSibling, mendelian ? null : "Chance a child inherits the allele, from the patient genotype");
  setLabel(priorEl.previousElementSibling, mendelian ? null : "Allele Frequency (gnomAD)");
  setLabel(
    riskUnscreenedEl.previousElementSibling,
    !mendelian ? "Child Inherits vs Unscreened Partner" : recessive ? "Risk vs Unscreened Partner (genotype probability)" : null
  );
  setLabel(
    riskCarrierEl.previousElementSibling,
    !mendelian ? "Child Inherits vs Wild-Type Partner" : recessive ? "Risk vs Carrier Partner (genotype probability)" : null
  );
  setLabel(simTitle && simTitle.firstElementChild, mendelian ? null : "Offspring Allele Simulator:");
  setLabel(simTitle && simTitle.lastElementChild, "Select Partner Genotype");
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

  if (modeBadge) {
    modeBadge.textContent = MODEL_LABELS[seg.model] ?? seg.model;
    if (seg.model === "autosomal_recessive") {
      modeBadge.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border bg-amber-50 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-500/30 font-mono";
    } else if (seg.model === "autosomal_dominant") {
      modeBadge.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border bg-rose-50 dark:bg-rose-500/20 text-rose-800 dark:text-rose-300 border-rose-300 dark:border-rose-500/30 font-mono";
    } else {
      modeBadge.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border bg-purple-50 dark:bg-purple-500/20 text-purple-800 dark:text-purple-300 border-purple-300 dark:border-purple-500/30 font-mono";
    }
  }

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
    b.className = b === active
      ? "partner-sim-btn px-2 py-1.5 rounded-sm text-center font-bold bg-sky-600 text-white border border-sky-600 shadow-sm transition-all"
      : "partner-sim-btn px-2 py-1.5 rounded-sm text-center font-bold bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 hover:border-sky-500 transition-all";
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
const SIM_BUTTON_LABELS = { unscreened: "Unscreened", carrier: "Heterozygous", affected: "Homozygous", wildtype: "Wild-Type" };

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
    { id: "affected", label: "Affected Probability:", value: null },
    { id: "carrier", label: "Carrier Probability:", value: null },
    { id: "wildtype", label: "Wild-Type / Non-Carrier:", value: null }
  ];
  let effective = null;
  let effectiveLabel = "Effective Penetrance Adjusted:";
  let reason = "";
  if (out && !out.available) {
    reason = out.reason;
  } else if (out && out.kind === "transmission") {
    rows[0] = { id: "affected", label: `${out.label}:`, value: out.inherits_allele };
    rows[1] = { id: "carrier", label: "Inherits One Copy:", value: out.one_copy };
    rows[2] = { id: "wildtype", label: "Inherits No Copy:", value: out.none };
    effective = "Not applicable";
    effectiveLabel = "Clinical Penetrance:";
  } else if (out && seg.model === "autosomal_recessive") {
    // Two different "affected" figures: the genotype probability (two copies), and that probability times the stated penetrance.
    rows[0] = { id: "affected", label: "Affected Genotype Probability (two copies):", value: out.affected };
    rows[1].value = out.carrier;
    rows[2].value = out.p0;
    effectiveLabel = "Affected Probability (adjusted for stated penetrance):";
    const adjusted = penetranceAdjustedAffected(out, seg.penetrance);
    effective = adjusted === null ? null : fmtPct(adjusted);
  } else if (out) {
    rows[0] = { id: "affected", label: "Affected Probability (penetrance-adjusted):", value: out.affected };
    rows[1] = { id: "carrier", label: "Inherits One Copy:", value: out.p1 };
    rows[2] = { id: "wildtype", label: "Does Not Inherit:", value: out.p0 };
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

function plddtClass(value) {
  if (value >= 85) return "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/30";
  if (value >= 70) return "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30";
  return "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30";
}

function renderDrawerBiotools(record) {
  const b = record.biotools;
  const geneBadge = document.getElementById("drawer-biotool-gene-badge");
  if (geneBadge) geneBadge.textContent = record.gene;

  // AlphaFold
  setValue(document.getElementById("drawer-af-uniprot"), b.uniprot);

  const plddtEl = document.getElementById("drawer-af-plddt");
  if (plddtEl) {
    setValue(plddtEl, b.plddt === null ? null : b.plddt.toFixed(1));
    plddtEl.className = b.plddt === null
      ? "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700"
      : plddtClass(b.plddt);
  }

  setValue(document.getElementById("drawer-af-status"), b.status);

  const domainsEl = document.getElementById("drawer-af-domains");
  if (domainsEl) {
    domainsEl.innerHTML = "";
    if (b.domains.length > 0) {
      b.domains.forEach(d => {
        const div = document.createElement("div");
        div.className = "p-1.5 rounded-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[10px]";
        div.textContent = `📍 ${d}`;
        domainsEl.appendChild(div);
      });
    } else {
      domainsEl.innerHTML = `<div class="text-xs">${naHtml()}</div>`;
    }
  }

  setValue(document.getElementById("drawer-af-joints"), b.joints === null ? null : `⚡ ${b.joints}`);

  // Ensembl VEP
  setValue(document.getElementById("drawer-ens-transcript"), b.transcript);
  setValue(document.getElementById("drawer-ens-alphamissense"), b.alphamissense);
  setValue(document.getElementById("drawer-ens-loeuf"), b.constraint);

  // ENCODE cCREs
  const encodeEl = document.getElementById("drawer-encode-tissues");
  if (encodeEl) {
    encodeEl.innerHTML = "";
    if (b.tissues.length === 0) {
      encodeEl.innerHTML = `<div class="text-xs">${naHtml()}</div>`;
      return;
    }
    // The bars are scaled to the largest value, with a floor of 100 TPM so a small value does not fill the bar.
    const maxTpm = Math.max(...b.tissues.map(([, tpm]) => tpm), 100);

    b.tissues.forEach(([tissue, tpm]) => {
      const pct = Math.round((tpm / maxTpm) * 100);
      const row = document.createElement("div");
      row.className = "space-y-0.5";
      row.innerHTML = `
        <div class="flex justify-between items-center text-[10px]">
          <span class="capitalize text-slate-700 dark:text-slate-300 font-medium">${escapeHtml(tissue)}</span>
          <span class="font-bold text-emerald-600 dark:text-emerald-400 font-mono">${escapeHtml(tpm.toLocaleString())} TPM</span>
        </div>
        <div class="w-full bg-slate-200 dark:bg-slate-800 h-1 rounded-none overflow-hidden">
          <div class="bg-emerald-500 h-1" style="width: ${pct}%"></div>
        </div>
      `;
      encodeEl.appendChild(row);
    });
  }
}

function closeDrawer() {
  const drawer = document.getElementById("variant-drawer");
  if (drawer) drawer.classList.add("translate-x-full");
  state.selectedVariant = null;
  // Return focus to whatever opened the drawer (a table row, or a button), if it is still on the page.
  if (drawerOpener && drawerOpener.isConnected) drawerOpener.focus();
  drawerOpener = null;
}

/** Every row the file produced, once each: observed findings first, then wild-type, gaps and insufficient evidence. */
function allRows() {
  const seen = new Set();
  return [...state.records, ...state.negativeChecks, ...state.arrayGaps, ...state.insufficientEvidence]
    .filter((vm) => !seen.has(vm.id) && seen.add(vm.id));
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
