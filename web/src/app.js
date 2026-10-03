/**
 * GenomePulse - Main Frontend Application Logic
 * =============================================
 * Orchestrates Web Worker file parsing, reactive UI updates,
 * compound APOE diplotype synthesis, light/dark mode theming,
 * filtering, sorting, variant inspection drawer, and Redis enrichment.
 */

import { simulateOffspringPedigree, BIOTOOLS_GENE_INSIGHTS, computeSegregationReport, KB_MANIFEST, ABSENCE_OF_FINDING_GUARDRAIL } from "./knowledge-base.js";

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
  compoundHeterozygotes: [],
  independentAssortment: [],
  selectedVariant: null,
  filterCategory: "all",
  searchQuery: "",
  sortBy: "magnitude",
  redisStats: null,
  theme: localStorage.getItem("genomepulse-theme") || "light"
};

// Initialize Application (handles both pre- and post-DOMContentLoaded module execution)
function initApp() {
  console.log("initApp executed, readyState:", document.readyState);
  initTheme();
  initEventListeners();
  window.__genomePulse = {
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
  localStorage.setItem("genomepulse-theme", theme);
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

// One worker per analysis run: a worker that failed (or never answers) is
// terminated and the next run starts fresh, so a retry can never hang on a dead one.
function startWorker() {
  stopWorker();
  const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  state.worker = worker;
  const fail = (message) => {
    if (state.worker !== worker) return;
    stopWorker();
    showAnalysisError(message);
  };

  worker.onerror = (err) => {
    fail((err && err.message) || "The analysis worker failed to start.");
  };
  worker.onmessageerror = () => {
    fail("The analysis worker sent a message the page could not read.");
  };
  worker.onmessage = (e) => {
    if (state.worker !== worker) return;
    clearWatchdog();
    const data = e.data;
    if (data.type === "progress") {
      armWatchdog(fail);
      updateProgress(data.percent, data.status);
    } else if (data.type === "complete") {
      stopWorker();
      handleParseComplete(data);
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

function showAnalysisError(message) {
  document.getElementById("progress-section").classList.add("hidden");
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
        showError(err.message);
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
      const apoeRec = state.records.find(r => r.rsid === "APOE-STATUS") || state.records.find(r => r.gene === "APOE");
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
    showError("Failed to read file from disk.");
  };
  reader.readAsText(file);
}

function processText(text, fileName) {
  document.getElementById("analysis-error").classList.add("hidden");
  setInputsDisabled(true);
  document.getElementById("progress-section").classList.remove("hidden");
  document.getElementById("results-section").classList.add("hidden");
  startWorker().postMessage({ action: "parse", text, fileName });
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
  state.qc = data.qc;
  state.records = data.records;
  state.negativeChecks = data.negative_checks || [];
  state.arrayGaps = data.array_gaps || [];
  state.insufficientEvidence = data.insufficient_evidence || [];
  state.coverageSummary = data.coverage_taxonomy || {};
  state.summary = data.summary;
  state.apoe = data.apoe;
  state.compoundHeterozygotes = data.compound_heterozygotes || [];
  state.independentAssortment = data.independent_assortment || [];

  document.getElementById("progress-section").classList.add("hidden");
  document.getElementById("analysis-error").classList.add("hidden");
  document.getElementById("results-section").classList.remove("hidden");
  setInputsDisabled(false);

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
  document.getElementById("qc-call-rate").textContent = `${(qc.call_rate * 100).toFixed(2)}%`;
  document.getElementById("qc-het-rate").textContent = `${(qc.heterozygosity_rate * 100).toFixed(2)}%`;

  // The badge shows the QC signal verbatim; it makes no sex or karyotype claim.
  const sexBadge = document.getElementById("qc-inferred-sex");
  sexBadge.textContent = qc.sex_signal;
  sexBadge.title = `X markers: ${qc.x_markers.toLocaleString()} | X heterozygosity: ${(qc.x_het_rate * 100).toFixed(1)}% | Y calls: ${qc.y_calls.toLocaleString()}`;
  sexBadge.className = "inline-flex items-center px-3 py-1 rounded-sm text-xs font-semibold bg-slate-200 dark:bg-slate-500/20 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-500/30";
}

function renderSummaryCards() {
  const sum = state.summary;
  if (!sum) return;

  document.getElementById("count-pathogenic").textContent = sum.pathogenic_count;
  document.getElementById("count-carrier").textContent = sum.carrier_count;
  document.getElementById("count-pgx").textContent = sum.pgx_count;
  document.getElementById("count-risk").textContent = sum.risk_factor_count;
  document.getElementById("count-acmg").textContent = sum.acmg_actionable_findings;

  const cov = state.coverageSummary || {};
  const elObs = document.getElementById("count-state-observed");
  if (elObs) elObs.textContent = (cov.supported_and_observed_count ?? state.records.length);

  const elNeg = document.getElementById("count-state-negative");
  if (elNeg) elNeg.textContent = (cov.supported_not_observed_count ?? state.negativeChecks.length);

  const elGaps = document.getElementById("count-state-gaps");
  if (elGaps) elGaps.textContent = (cov.not_tested_by_array_count ?? state.arrayGaps.length);

  const elOut = document.getElementById("count-state-outside");
  if (elOut) elOut.textContent = (cov.outside_coverage_count ?? 0).toLocaleString();

  const elIns = document.getElementById("count-state-insufficient");
  if (elIns) elIns.textContent = (cov.insufficient_evidence_count ?? state.insufficientEvidence.length);
}

function renderApoeCard() {
  const card = document.getElementById("apoe-status-card");
  if (!card) return;

  if (!state.apoe) {
    card.classList.add("hidden");
    return;
  }

  card.classList.remove("hidden");
  const apoe = state.apoe;

  const titleEl = document.getElementById("apoe-diplotype-title");
  const riskRatioEl = document.getElementById("apoe-risk-ratio");
  const descEl = document.getElementById("apoe-phenotype-desc");
  const rawLociEl = document.getElementById("apoe-raw-loci");
  const lifetimeEl = document.getElementById("apoe-lifetime-stat");
  const pillEl = document.getElementById("apoe-carrier-pill");

  titleEl.textContent = `APOE ${apoe.diplotype} (${apoe.label.replace(/^APOE\s*/, "")})`;
  riskRatioEl.textContent = apoe.riskRatio;
  descEl.textContent = apoe.phenotype;
  rawLociEl.textContent = apoe.rawSummary;
  lifetimeEl.textContent = apoe.lifetimeRisk;

  // Visual accents depending on risk profile
  if (apoe.diplotype === "ε4/ε4") {
    card.className = "glass-panel p-6 border-l-4 border-rose-500 transition-all duration-200 bg-white dark:bg-slate-900/60";
    riskRatioEl.className = "px-2.5 py-1 text-xs font-bold rounded-sm font-mono border badge-pathogenic";
    pillEl.className = "px-2 py-0.5 text-[11px] font-bold uppercase rounded-sm border badge-pathogenic";
    pillEl.textContent = "High Risk Locus";
  } else if (apoe.diplotype === "ε3/ε4" || apoe.diplotype.includes("ε4")) {
    card.className = "glass-panel p-6 border-l-4 border-amber-500 transition-all duration-200 bg-white dark:bg-slate-900/60";
    riskRatioEl.className = "px-2.5 py-1 text-xs font-bold rounded-sm font-mono border badge-carrier";
    pillEl.className = "px-2 py-0.5 text-[11px] font-bold uppercase rounded-sm border badge-carrier";
    pillEl.textContent = "Carrier Status";
  } else if (apoe.diplotype.includes("ε2")) {
    card.className = "glass-panel p-6 border-l-4 border-purple-500 transition-all duration-200 bg-white dark:bg-slate-900/60";
    riskRatioEl.className = "px-2.5 py-1 text-xs font-bold rounded-sm font-mono border badge-pgx";
    pillEl.className = "px-2 py-0.5 text-[11px] font-bold uppercase rounded-sm border badge-pgx";
    pillEl.textContent = "Neuroprotective / Carrier";
  } else {
    // Normal baseline (e3/e3)
    card.className = "glass-panel p-6 border-l-4 border-emerald-500 transition-all duration-200 bg-white dark:bg-slate-900/60";
    riskRatioEl.className = "px-2.5 py-1 text-xs font-bold rounded-sm font-mono border badge-benign";
    pillEl.className = "px-2 py-0.5 text-[11px] font-bold uppercase rounded-sm border badge-benign";
    pillEl.textContent = "Normal Baseline";
  }
}

function renderAssortmentSection() {
  const section = document.getElementById("assortment-section");
  const container = document.getElementById("assortment-cards-container");
  const badge = document.getElementById("assortment-findings-count-badge");
  if (!section || !container) return;

  const compounds = state.compoundHeterozygotes || [];
  const assortments = state.independentAssortment || [];
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

  // Render Compound Heterozygotes (e.g. HFE C282Y / H63D)
  compounds.forEach(ch => {
    const card = document.createElement("div");
    card.className = "p-4 rounded-sm bg-slate-50 dark:bg-slate-900/50 border border-indigo-200 dark:border-indigo-900/60 space-y-3";
    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="text-xs uppercase font-bold tracking-wider text-indigo-700 dark:text-indigo-400 font-mono">Trans Phase Compound Heterozygote</span>
          <span class="px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border badge-pathogenic">${ch.significance}</span>
        </div>
        <span class="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">${ch.gene}</span>
      </div>
      <div>
        <h4 class="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono">${ch.title}</h4>
        <p class="text-xs text-slate-600 dark:text-slate-400 font-serif mt-1">${ch.summary}</p>
      </div>
      <div class="p-2.5 rounded-sm bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800/40 text-[11px] font-mono text-indigo-900 dark:text-indigo-300">
        ⚖️ <strong>Segregation:</strong> ${ch.segregation_notes}
      </div>
      <div class="flex justify-end pt-1">
        <button type="button" class="btn btn-xs btn-outline border-indigo-400 dark:border-indigo-600 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-500/10 rounded-sm font-mono text-[11px] btn-inspect-gene" data-gene="${ch.gene}">
          🔬 Inspect ${ch.gene} Locus ↗
        </button>
      </div>
    `;
    container.appendChild(card);
  });

  // Render Independent Assortment Pairs (e.g. F5 Chr 1 + F2 Chr 11)
  assortments.forEach(ia => {
    const card = document.createElement("div");
    card.className = "p-4 rounded-sm bg-slate-50 dark:bg-slate-900/50 border border-amber-200 dark:border-amber-900/60 space-y-3";
    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="text-xs uppercase font-bold tracking-wider text-amber-700 dark:text-amber-400 font-mono">Independent Assortment · Mendel's 2nd Law</span>
          <span class="px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border badge-risk">Joint Multi-Locus Risk</span>
        </div>
        <span class="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">${ia.genes.join(" + ")}</span>
      </div>
      <div>
        <h4 class="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono">${ia.type}</h4>
        <p class="text-xs text-slate-600 dark:text-slate-400 font-serif mt-1">${ia.description}</p>
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs font-mono">
        <div class="p-2 rounded-sm bg-white dark:bg-slate-950 border border-amber-200 dark:border-amber-800/40">
          <span class="text-[9px] uppercase text-slate-400 block">Loci Unlinked Chromosomes</span>
          <span class="font-bold text-slate-800 dark:text-slate-200 mt-0.5 block">${ia.loci.join(" · ")}</span>
        </div>
        <div class="p-2 rounded-sm bg-white dark:bg-slate-950 border border-amber-200 dark:border-amber-800/40">
          <span class="text-[9px] uppercase text-slate-400 block">Offspring Joint Probability</span>
          <span class="font-bold text-amber-600 dark:text-amber-400 mt-0.5 block">${Math.round(ia.joint_transmission_prob * 100)}% (0.50 × 0.50)</span>
        </div>
      </div>
      <div class="flex justify-end space-x-2 pt-1">
        ${ia.genes.map(g => `
          <button type="button" class="btn btn-xs btn-outline border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-amber-500 rounded-sm font-mono text-[11px] btn-inspect-gene" data-gene="${g}">
            Inspect ${g} ↗
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
    if (state.filterCategory === "risk" && (r.category !== "Risk Factor" && !(r.apoeInfo && (r.apoeInfo.diplotype === "ε3/ε4" || r.apoeInfo.diplotype === "ε4/ε4")))) return false;
    if (state.filterCategory === "acmg" && !r.acmg_actionable) return false;

    // Search query
    if (state.searchQuery) {
      const q = state.searchQuery;
      const match = (
        r.rsid.toLowerCase().includes(q) ||
        r.gene.toLowerCase().includes(q) ||
        (r.phenotype && r.phenotype.toLowerCase().includes(q)) ||
        (r.genotype && r.genotype.toLowerCase().includes(q)) ||
        (r.category && r.category.toLowerCase().includes(q)) ||
        (r.significance && r.significance.toLowerCase().includes(q)) ||
        (r.drug_response && r.drug_response.toLowerCase().includes(q)) ||
        (r.apoeInfo && (r.apoeInfo.label.toLowerCase().includes(q) || r.apoeInfo.diplotype.toLowerCase().includes(q)))
      );
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
    tr.onclick = () => openDrawer(r);

    let categoryClass = "badge-benign";
    if (r.category === "Pathogenic") categoryClass = "badge-pathogenic";
    else if (r.category === "Carrier" || r.isCarrier) categoryClass = "badge-carrier";
    else if (r.category === "Pharmacogenomics") categoryClass = "badge-pgx";
    else if (r.category === "Risk Factor") categoryClass = "badge-risk";

    // Coverage State badge
    let stateBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30">Observed</span>`;
    if (r.coverage_state === "supported_not_observed") {
      stateBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/30">Tested WT</span>`;
    } else if (r.coverage_state === "not_tested_by_array") {
      stateBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30">Array Gap</span>`;
    } else if (r.coverage_state === "insufficient_evidence") {
      stateBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300 border border-rose-300 dark:border-rose-500/30">Conflicting</span>`;
    }

    // Evidence Tier badge
    let tierBadge = "";
    const tier = r.evidence_tier || "Tier B";
    if (tier === "Tier A") {
      tierBadge = `<span class="px-1.5 py-0.5 rounded-sm text-[10px] font-bold uppercase font-mono bg-sky-100 text-sky-800 border border-sky-300 dark:bg-sky-900/40 dark:text-sky-300 dark:border-sky-700 mr-1.5">Tier A</span>`;
    } else if (tier === "Tier B") {
      tierBadge = `<span class="px-1.5 py-0.5 rounded-sm text-[10px] font-bold uppercase font-mono bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-700 mr-1.5">Tier B</span>`;
    } else if (tier === "Tier C") {
      tierBadge = `<span class="px-1.5 py-0.5 rounded-sm text-[10px] font-bold uppercase font-mono bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700 mr-1.5">Tier C</span>`;
    } else if (tier === "Tier D") {
      tierBadge = `<span class="px-1.5 py-0.5 rounded-sm text-[10px] font-bold uppercase font-mono bg-slate-100 text-slate-700 border border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700 mr-1.5">Tier D</span>`;
    }

    const starsHtml = r.clinvar_stars ? "★".repeat(r.clinvar_stars) : "—";
    const acmgPill = r.acmg_actionable 
      ? `<span class="ml-1.5 px-1.5 py-0.5 text-[10px] uppercase font-bold rounded-sm bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30">ACMG</span>` 
      : "";

    const magnitudeDisplay = typeof r.magnitude === "number" ? r.magnitude.toFixed(1) : "—";
    const reputeDisplay = r.repute ? `(${r.repute})` : "";

    tr.innerHTML = `
      <td class="py-3 px-4 font-mono font-bold text-sky-700 dark:text-sky-400">${r.rsid}</td>
      <td class="py-3 px-4 font-semibold text-slate-900 dark:text-slate-100">
        ${r.gene} ${acmgPill}
      </td>
      <td class="py-3 px-4 font-mono font-bold text-slate-900 dark:text-slate-100">${r.genotype || '—'}</td>
      <td class="py-3 px-4">${stateBadge}</td>
      <td class="py-3 px-4 flex items-center">
        ${tierBadge}
        <span class="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-semibold ${categoryClass}">
          ${r.category || 'Curated'}
        </span>
      </td>
      <td class="py-3 px-4 text-amber-500 text-xs font-mono tracking-wider">${starsHtml}</td>
      <td class="py-3 px-4 font-semibold text-xs ${typeof r.magnitude === 'number' && r.magnitude >= 4 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-700 dark:text-slate-300'}">
        ${magnitudeDisplay} <span class="text-[10px] text-slate-400">${reputeDisplay}</span>
      </td>
      <td class="py-3 px-4 text-xs text-slate-700 dark:text-slate-300 max-w-md truncate" title="${r.phenotype || r.significance}">
        ${r.phenotype || r.significance}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openDrawer(record) {
  state.selectedVariant = record;
  const drawer = document.getElementById("variant-drawer");
  if (!drawer) return;

  document.getElementById("drawer-rsid").textContent = record.rsid;
  document.getElementById("drawer-gene").textContent = record.gene;
  document.getElementById("drawer-genotype").textContent = record.genotype || "—";
  document.getElementById("drawer-coord").textContent = `chr${record.chrom}:${record.pos ? record.pos.toLocaleString() : '—'}`;
  document.getElementById("drawer-significance").textContent = record.significance;
  document.getElementById("drawer-phenotype").textContent = record.phenotype;
  const stars = record.clinvar_stars ?? 0;
  document.getElementById("drawer-stars").textContent = stars > 0 ? `${"★".repeat(stars)} (${stars} / 4 stars)` : "— (0 / 4 stars)";
  document.getElementById("drawer-magnitude").textContent = `${typeof record.magnitude === 'number' ? record.magnitude.toFixed(1) : '—'} / 10.0 (${record.repute || 'Neutral'})`;
  const afEl = document.getElementById("drawer-af");
  if (afEl) {
    if (record.gnomad_af !== null && record.gnomad_af !== undefined && !isNaN(record.gnomad_af)) {
      afEl.textContent = `${(record.gnomad_af * 100).toFixed(2)}%`;
    } else {
      afEl.textContent = "N/A (Not characterized)";
    }
  }

  // Tier and Coverage State badges
  const tierBadgeEl = document.getElementById("drawer-tier-badge");
  const covBadgeEl = document.getElementById("drawer-coverage-state-badge");
  if (tierBadgeEl) {
    const tier = record.evidence_tier || "Tier D";
    tierBadgeEl.textContent = tier;
    if (tier === "Tier A") {
      tierBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300 border-sky-300 dark:border-sky-500/30";
    } else if (tier === "Tier B") {
      tierBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30";
    } else if (tier === "Tier C") {
      tierBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border-amber-300 dark:border-amber-500/30";
    } else {
      tierBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300 border-slate-300 dark:border-slate-700";
    }
  }

  if (covBadgeEl) {
    const cov = record.coverage_state || "supported_and_observed";
    if (cov === "supported_and_observed") {
      covBadgeEl.textContent = "Supported & Observed";
      covBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300 border-sky-300 dark:border-sky-500/30";
    } else if (cov === "supported_not_observed") {
      covBadgeEl.textContent = "Tested Wild-Type (State 2)";
      covBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30";
    } else if (cov === "not_tested_by_array") {
      covBadgeEl.textContent = "Array Gap (State 3)";
      covBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border-amber-300 dark:border-amber-500/30";
    } else if (cov === "insufficient_evidence") {
      covBadgeEl.textContent = "Conflicting Evidence (State 5)";
      covBadgeEl.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border font-mono bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300 border-rose-300 dark:border-rose-500/30";
    } else {
      covBadgeEl.textContent = cov;
    }
  }

  // Refusal notices (e.g. Star-Allele refusal)
  const refusalBox = document.getElementById("drawer-refusal-box");
  const refusalText = document.getElementById("drawer-refusal-text");
  if (refusalBox && refusalText) {
    if (record.refusal_notices && record.refusal_notices.length > 0) {
      refusalBox.classList.remove("hidden");
      refusalText.textContent = record.refusal_notices.join(" ");
    } else if (record.category === "Pharmacogenomics") {
      refusalBox.classList.remove("hidden");
      refusalText.textContent = "Incomplete star-allele coverage refusal: Interrogating an isolated single SNP cannot rule out other functional star alleles (*3, *17, etc.). A complete CPIC metabolizer phenotype cannot be inferred from a single variant call.";
    } else {
      refusalBox.classList.add("hidden");
    }
  }

  // Caveats list
  const caveatsBox = document.getElementById("drawer-caveats-box");
  const caveatsList = document.getElementById("drawer-caveats-list");
  if (caveatsBox && caveatsList) {
    const caveats = record.caveats || [];
    if (caveats.length > 0) {
      caveatsBox.classList.remove("hidden");
      caveatsList.innerHTML = caveats.map(c => `<li>${c}</li>`).join("");
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
  if (record.drug_response) {
    drugBox.classList.remove("hidden");
    drugText.textContent = record.drug_response;
  } else {
    drugBox.classList.add("hidden");
  }

  // ClinVar external link
  const clinvarLink = document.getElementById("drawer-clinvar-link");
  if (record.clinvar_id) {
    clinvarLink.href = `https://www.ncbi.nlm.nih.gov/clinvar/variation/${record.clinvar_id.replace(/\D/g, "")}`;
    clinvarLink.classList.remove("hidden");
  } else if (record.gene === "APOE") {
    clinvarLink.href = `https://www.ncbi.nlm.nih.gov/clinvar/variation/17864/`;
    clinvarLink.classList.remove("hidden");
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
  if (record.hpa_tissues && Object.keys(record.hpa_tissues).length > 0) {
    Object.entries(record.hpa_tissues).forEach(([tissue, level]) => {
      let colorClass = "bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300 border-sky-300 dark:border-sky-500/30";
      if (level === "High") colorClass = "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30";
      else if (level === "Medium") colorClass = "bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-500/30";

      const div = document.createElement("div");
      div.className = "flex items-center justify-between p-2 rounded-sm bg-slate-100 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/50 text-xs";
      div.innerHTML = `
        <span class="capitalize text-slate-800 dark:text-slate-200 font-medium">${tissue}</span>
        <span class="px-2 py-0.5 rounded-sm text-[11px] font-semibold border ${colorClass}">${level}</span>
      `;
      tissuesContainer.appendChild(div);
    });
  } else {
    tissuesContainer.innerHTML = `<p class="text-xs text-slate-500 dark:text-slate-400">Normal protein abundance widely expressed across human tissues.</p>`;
  }

  // Subcellular localization
  const subcellContainer = document.getElementById("drawer-hpa-subcell");
  subcellContainer.innerHTML = "";
  if (record.hpa_subcellular && record.hpa_subcellular.length > 0) {
    record.hpa_subcellular.forEach(loc => {
      const span = document.createElement("span");
      span.className = "px-2.5 py-1 rounded-sm text-xs font-medium bg-purple-100 dark:bg-purple-500/15 text-purple-800 dark:text-purple-300 border border-purple-300 dark:border-purple-500/30 font-mono";
      span.textContent = loc;
      subcellContainer.appendChild(span);
    });
  } else {
    subcellContainer.innerHTML = `<span class="text-xs text-slate-500 dark:text-slate-400">Cytosol / Nucleus</span>`;
  }

  // Show drawer
  drawer.classList.remove("translate-x-full");
}

function renderDrawerSegregation(record) {
  const seg = record.segregation || (record.gene ? computeSegregationReport(record.gene, record.genotype, record.category, record.significance) : null);
  const modeBadge = document.getElementById("drawer-seg-mode-badge");
  const priorEl = document.getElementById("drawer-seg-carrier-prior");
  const penetranceEl = document.getElementById("drawer-seg-penetrance");
  const riskUnscreenedEl = document.getElementById("drawer-seg-risk-unscreened");
  const riskCarrierEl = document.getElementById("drawer-seg-risk-carrier");

  if (!seg) {
    if (modeBadge) modeBadge.textContent = "Complex";
    if (priorEl) priorEl.textContent = "N/A";
    if (penetranceEl) penetranceEl.textContent = "Variable";
    if (riskUnscreenedEl) riskUnscreenedEl.textContent = "N/A";
    if (riskCarrierEl) riskCarrierEl.textContent = "N/A";
    updateSimulator("unscreened", record.gene);
    return;
  }

  if (modeBadge) {
    modeBadge.textContent = seg.mode;
    if (seg.mode.includes("Recessive")) {
      modeBadge.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border bg-amber-50 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-500/30 font-mono";
    } else if (seg.mode.includes("Dominant")) {
      modeBadge.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border bg-rose-50 dark:bg-rose-500/20 text-rose-800 dark:text-rose-300 border-rose-300 dark:border-rose-500/30 font-mono";
    } else {
      modeBadge.className = "px-2 py-0.5 text-[10px] font-bold uppercase rounded-sm border bg-purple-50 dark:bg-purple-500/20 text-purple-800 dark:text-purple-300 border-purple-300 dark:border-purple-500/30 font-mono";
    }
  }

  const priorPct = (seg.partner_carrier_prior * 100).toFixed(1);
  const priorFraction = Math.round(1 / (seg.partner_carrier_prior || 0.02));
  if (priorEl) priorEl.textContent = `1 in ${priorFraction} (${priorPct}%)`;
  if (penetranceEl) penetranceEl.textContent = `${Math.round((seg.penetrance || 1.0) * 100)}%`;

  const unscreenedPct = (seg.offspring_risk_unscreened * 100).toFixed(1);
  const unscreenedFraction = seg.offspring_risk_unscreened > 0 ? Math.round(1 / seg.offspring_risk_unscreened) : 0;
  if (riskUnscreenedEl) riskUnscreenedEl.textContent = unscreenedFraction > 0 ? `${unscreenedPct}% (1 in ${unscreenedFraction})` : "Baseline";

  const carrierPct = (seg.offspring_risk_carrier * 100).toFixed(1);
  const carrierFraction = seg.offspring_risk_carrier > 0 ? Math.round(1 / seg.offspring_risk_carrier) : 0;
  if (riskCarrierEl) riskCarrierEl.textContent = carrierFraction > 0 ? `${carrierPct}% (1 in ${carrierFraction})` : "N/A";

  // Setup simulator partner buttons
  const buttons = document.querySelectorAll(".partner-sim-btn");
  buttons.forEach(btn => {
    btn.onclick = () => {
      buttons.forEach(b => {
        b.className = "partner-sim-btn px-2 py-1.5 rounded-sm text-center font-bold bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 hover:border-sky-500 transition-all";
      });
      btn.className = "partner-sim-btn px-2 py-1.5 rounded-sm text-center font-bold bg-sky-600 text-white border border-sky-600 shadow-sm transition-all";
      const partner = btn.getAttribute("data-partner");
      updateSimulator(partner, record.gene);
    };
  });

  // Reset to unscreened active button
  buttons.forEach(b => {
    if (b.getAttribute("data-partner") === "unscreened") {
      b.className = "partner-sim-btn px-2 py-1.5 rounded-sm text-center font-bold bg-sky-600 text-white border border-sky-600 shadow-sm transition-all";
    } else {
      b.className = "partner-sim-btn px-2 py-1.5 rounded-sm text-center font-bold bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 hover:border-sky-500 transition-all";
    }
  });

  updateSimulator("unscreened", record.gene);
}

function updateSimulator(partner, gene) {
  const sim = simulateOffspringPedigree(gene, partner);

  const affEl = document.getElementById("sim-p-affected");
  const barAffEl = document.getElementById("sim-bar-affected");
  if (affEl) affEl.textContent = `${sim.pAffected}%`;
  if (barAffEl) barAffEl.style.width = `${Math.min(100, Math.max(1, sim.pAffected))}%`;

  const carrEl = document.getElementById("sim-p-carrier");
  const barCarrEl = document.getElementById("sim-bar-carrier");
  if (carrEl) carrEl.textContent = `${sim.pCarrier}%`;
  if (barCarrEl) barCarrEl.style.width = `${Math.min(100, Math.max(1, sim.pCarrier))}%`;

  const wtEl = document.getElementById("sim-p-wildtype");
  const barWtEl = document.getElementById("sim-bar-wildtype");
  if (wtEl) wtEl.textContent = `${sim.pWildtype}%`;
  if (barWtEl) barWtEl.style.width = `${Math.min(100, Math.max(1, sim.pWildtype))}%`;

  const effEl = document.getElementById("sim-effective-risk");
  if (effEl) effEl.textContent = `${sim.effectiveClinicalRisk}% (${sim.mode})`;
}

function renderDrawerBiotools(record) {
  const gene = record.gene;
  const biotools = record.segregation?.biotools || BIOTOOLS_GENE_INSIGHTS[gene];
  const geneBadge = document.getElementById("drawer-biotool-gene-badge");

  if (geneBadge) geneBadge.textContent = gene;

  if (!biotools) {
    const uniprotEl = document.getElementById("drawer-af-uniprot");
    const plddtEl = document.getElementById("drawer-af-plddt");
    const statusEl = document.getElementById("drawer-af-status");
    const domainsEl = document.getElementById("drawer-af-domains");
    const jointsEl = document.getElementById("drawer-af-joints");
    const transEl = document.getElementById("drawer-ens-transcript");
    const amEl = document.getElementById("drawer-ens-alphamissense");
    const loeufEl = document.getElementById("drawer-ens-loeuf");
    const encodeEl = document.getElementById("drawer-encode-tissues");

    if (uniprotEl) uniprotEl.textContent = "UniProt Search";
    if (plddtEl) plddtEl.textContent = "N/A";
    if (statusEl) statusEl.textContent = "Structural prediction available via AlphaFold Protein Structure Database.";
    if (domainsEl) domainsEl.innerHTML = `<div class="text-xs text-slate-500">Query AlphaFold DB for ${gene} residue coordinates.</div>`;
    if (jointsEl) jointsEl.textContent = "Flexible joints computed dynamically.";

    if (transEl) transEl.textContent = "MANE Select Pending";
    if (amEl) amEl.textContent = "Score Available in API";
    if (loeufEl) loeufEl.textContent = "Constraint Available";

    if (encodeEl) encodeEl.innerHTML = `<div class="text-xs text-slate-500">ENCODE cCREs RNA-seq available for major human cell types.</div>`;
    return;
  }

  // AlphaFold
  const uniprotEl = document.getElementById("drawer-af-uniprot");
  if (uniprotEl) uniprotEl.textContent = `UniProt ${biotools.uniprot_id}`;

  const plddtEl = document.getElementById("drawer-af-plddt");
  if (plddtEl) {
    const plddtVal = biotools.alphafold?.global_plddt ?? record.alphafold_plddt;
    if (plddtVal !== null && plddtVal !== undefined && !isNaN(plddtVal)) {
      plddtEl.textContent = Number(plddtVal).toFixed(1);
      if (plddtVal >= 85) {
        plddtEl.className = "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/30";
      } else if (plddtVal >= 70) {
        plddtEl.className = "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300 border border-sky-300 dark:border-sky-500/30";
      } else {
        plddtEl.className = "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-500/30";
      }
    } else {
      plddtEl.textContent = "N/A";
      plddtEl.className = "font-bold font-mono px-2 py-0.5 rounded-sm text-[11px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700";
    }
  }

  const statusEl = document.getElementById("drawer-af-status");
  if (statusEl) statusEl.textContent = biotools.alphafold?.folding_status || "Structural prediction available in AlphaFold DB.";

  const domainsEl = document.getElementById("drawer-af-domains");
  if (domainsEl) {
    domainsEl.innerHTML = "";
    const domains = biotools.alphafold?.domains || [];
    if (domains.length > 0) {
      domains.forEach(d => {
        const div = document.createElement("div");
        div.className = "p-1.5 rounded-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[10px]";
        div.textContent = `📍 ${d}`;
        domainsEl.appendChild(div);
      });
    } else {
      domainsEl.innerHTML = `<div class="text-xs text-slate-500">Domain boundaries computed from PAE matrix.</div>`;
    }
  }

  const jointsEl = document.getElementById("drawer-af-joints");
  if (jointsEl) jointsEl.textContent = biotools.alphafold?.flexible_joints ? `⚡ ${biotools.alphafold.flexible_joints}` : "Flexible inter-domain links";

  // Ensembl VEP
  const transEl = document.getElementById("drawer-ens-transcript");
  if (transEl) transEl.textContent = biotools.ensembl?.canonical_transcript || record.mane_transcript || "MANE Select Transcript";

  const amEl = document.getElementById("drawer-ens-alphamissense");
  if (amEl) {
    const amScore = biotools.ensembl?.alphamissense_pathogenicity ?? record.alphamissense_score;
    const amClass = biotools.ensembl?.alphamissense_class ?? record.alphamissense_class;
    if (amScore !== null && amScore !== undefined && !isNaN(amScore)) {
      amEl.textContent = `${amClass || 'Scored'} (${Number(amScore).toFixed(2)})`;
    } else if (amClass) {
      amEl.textContent = amClass;
    } else {
      amEl.textContent = "N/A (Non-missense)";
    }
  }

  const loeufEl = document.getElementById("drawer-ens-loeuf");
  if (loeufEl) {
    const loeufVal = biotools.ensembl?.loeuf ?? record.gnomad_loeuf;
    if (loeufVal !== null && loeufVal !== undefined && !isNaN(loeufVal)) {
      const loeufNum = Number(loeufVal);
      const loeufText = loeufNum < 0.35 
        ? `${loeufNum.toFixed(2)} (Extremely Constrained)` 
        : loeufNum < 0.75 
        ? `${loeufNum.toFixed(2)} (Constrained)` 
        : `${loeufNum.toFixed(2)} (Tolerant)`;
      loeufEl.textContent = `LOEUF ${loeufText}`;
    } else {
      loeufEl.textContent = "Constraint N/A";
    }
  }

  // ENCODE cCREs
  const encodeEl = document.getElementById("drawer-encode-tissues");
  if (encodeEl) {
    encodeEl.innerHTML = "";
    const tissues = biotools.encode.top_tissues || {};
    const maxTpm = Math.max(...Object.values(tissues), 100);

    Object.entries(tissues).forEach(([tissue, tpm]) => {
      const pct = Math.round((tpm / maxTpm) * 100);
      const row = document.createElement("div");
      row.className = "space-y-0.5";
      row.innerHTML = `
        <div class="flex justify-between items-center text-[10px]">
          <span class="capitalize text-slate-700 dark:text-slate-300 font-medium">${tissue}</span>
          <span class="font-bold text-emerald-600 dark:text-emerald-400 font-mono">${tpm.toLocaleString()} TPM</span>
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
}

function exportMarkdownReport() {
  if (!state.records || state.records.length === 0) return;
  const qc = state.qc;
  const apoe = state.apoe;
  const cov = state.coverageSummary || {};

  let md = `# GenomePulse Variome Clinical Report\n\n`;
  md += `> **CARDINAL SCOPE GUARDRAIL**: ${ABSENCE_OF_FINDING_GUARDRAIL}\n\n`;
  md += `**Sample**: ${state.fileName} | **Format**: ${qc.format_name.toUpperCase()} (${qc.build}) | **Sex-chromosome QC**: ${qc.sex_signal}\n`;
  md += `**Markers**: ${qc.total_snps.toLocaleString()} | **Call Rate**: ${(qc.call_rate * 100).toFixed(2)}% | **Heterozygosity**: ${(qc.heterozygosity_rate * 100).toFixed(2)}%\n\n`;

  md += `## Coverage Taxonomy (5-State Summary)\n\n`;
  md += `- **Supported & Observed (State 1)**: ${cov.supported_and_observed_count ?? state.records.length} findings\n`;
  md += `- **Tested Wild-Type / Supported Not Observed (State 2)**: ${cov.supported_not_observed_count ?? state.negativeChecks.length} loci\n`;
  md += `- **Microarray Gaps / Not Tested by Chip (State 3)**: ${cov.not_tested_by_array_count ?? state.arrayGaps.length} loci\n`;
  md += `- **Outside Coverage Scope (State 4)**: ${(cov.outside_coverage_count ?? 0).toLocaleString()} markers\n`;
  md += `- **Conflicting / Insufficient Evidence (State 5)**: ${cov.insufficient_evidence_count ?? state.insufficientEvidence.length} loci\n\n`;

  if (apoe) {
    md += `## APOE Neuro-Genomic Status\n`;
    md += `- **Diplotype**: APOE ${apoe.diplotype} (${apoe.label})\n`;
    md += `- **Risk Ratio**: ${apoe.riskRatio}\n`;
    md += `- **Estimated Lifetime Risk**: ${apoe.lifetimeRisk}\n`;
    md += `- **Underlying Loci**: ${apoe.rawSummary}\n`;
    md += `- **Clinical Guidance**: ${apoe.phenotype}\n\n`;
  }

  if (state.compoundHeterozygotes && state.compoundHeterozygotes.length > 0) {
    md += `## Multi-Locus Compound Heterozygotes (Trans Phase)\n\n`;
    state.compoundHeterozygotes.forEach(ch => {
      md += `### ${ch.title} (${ch.gene})\n`;
      md += `- **Significance**: ${ch.significance}\n`;
      md += `- **Clinical Summary**: ${ch.summary}\n`;
      md += `- **Segregation**: ${ch.segregation_notes}\n\n`;
    });
  }

  if (state.independentAssortment && state.independentAssortment.length > 0) {
    md += `## Multi-Locus Independent Assortment (Mendel's 2nd Law)\n\n`;
    state.independentAssortment.forEach(ia => {
      md += `### ${ia.type} (${ia.genes.join(" + ")})\n`;
      md += `- **Loci**: ${ia.loci.join(" · ")}\n`;
      md += `- **Joint Offspring Probability**: ${(ia.joint_transmission_prob * 100).toFixed(0)}%\n`;
      md += `- **Epistatic Interaction**: ${ia.description}\n\n`;
    });
  }

  md += `## Observed Clinical Findings (State 1)\n\n`;
  md += `| rsID | Gene | Genotype | State | Tier | Category | ClinVar | Magnitude | Phenotype / Guidance |\n`;
  md += `| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n`;

  state.records.forEach(r => {
    const stars = "★".repeat(r.clinvar_stars || 1);
    const tier = r.evidence_tier || "Tier B";
    md += `| ${r.rsid} | ${r.gene} | ${r.genotype || '—'} | ${r.coverage_state || 'supported_and_observed'} | ${tier} | ${r.category} | ${stars} | ${typeof r.magnitude === 'number' ? r.magnitude.toFixed(1) : '—'} | ${r.phenotype ? r.phenotype.replace(/\|/g, "/") : ''} |\n`;
  });

  if (state.negativeChecks && state.negativeChecks.length > 0) {
    md += `\n## Tested Wild-Type Loci (State 2: Supported but Not Observed)\n\n`;
    md += `| rsID | Gene | Genotype | State | Tier | Condition | Clinical Interpretation |\n`;
    md += `| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n`;
    state.negativeChecks.forEach(r => {
      const tier = r.evidence_tier || "Tier B";
      md += `| ${r.rsid} | ${r.gene} | ${r.genotype || '—'} | ${r.coverage_state} | ${tier} | ${r.condition || r.gene} | ${r.significance || 'Tested Wild-Type (Tested Normal)'} |\n`;
    });
  }

  if (state.arrayGaps && state.arrayGaps.length > 0) {
    md += `\n## Microarray Gaps (State 3: Not Tested by Chip)\n\n`;
    md += `| rsID | Gene | Build Coordinates | State | Clinical Significance / Locus Role |\n`;
    md += `| :--- | :--- | :--- | :--- | :--- |\n`;
    state.arrayGaps.forEach(r => {
      md += `| ${r.rsid} | ${r.gene} | chr${r.chrom}:${r.pos} | ${r.coverage_state} | ${r.significance || 'Array Gap (Locus not present on microarray)'} |\n`;
    });
  }

  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  downloadBlob(blob, `GenomePulse_Report_${Date.now()}.md`);
}

function exportCsvReport() {
  if (!state.records || state.records.length === 0) return;

  const headers = [
    "rsID", "Gene", "Genotype", "Chromosome", "Position", "Coverage_State", "Evidence_Tier",
    "Category", "Significance", "Magnitude", "Repute", "ClinVar_Stars", 
    "Inheritance_Mode", "Carrier_Prior_2pq", "Offspring_Risk_Unscreened", "Offspring_Risk_Carrier",
    "Condition_Phenotype", "Refusal_Notices", "Caveats"
  ];
  const rows = [headers.join(",")];

  const allExportRecords = [
    ...(state.records || []),
    ...(state.negativeChecks || []),
    ...(state.arrayGaps || [])
  ];

  allExportRecords.forEach(r => {
    const seg = r.segregation;
    const row = [
      `"${r.rsid}"`,
      `"${r.gene}"`,
      `"${r.genotype || '—'}"`,
      `"${r.chrom}"`,
      r.pos,
      `"${r.coverage_state || 'supported_and_observed'}"`,
      `"${r.evidence_tier || 'Tier B'}"`,
      `"${r.category || 'Curated'}"`,
      `"${r.significance || ''}"`,
      typeof r.magnitude === "number" ? r.magnitude : 0,
      `"${r.repute || 'Neutral'}"`,
      r.clinvar_stars || 0,
      `"${seg?.mode || 'N/A'}"`,
      seg ? seg.partner_carrier_prior : "N/A",
      seg ? seg.offspring_risk_unscreened : "N/A",
      seg ? seg.offspring_risk_carrier : "N/A",
      `"${(r.phenotype || '').replace(/"/g, '""')}"`,
      `"${(r.refusal_notices || []).join('; ').replace(/"/g, '""')}"`,
      `"${(r.caveats || []).join('; ').replace(/"/g, '""')}"`
    ];
    rows.push(row.join(","));
  });

  const blob = new Blob([rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
  downloadBlob(blob, `GenomePulse_Variants_${Date.now()}.csv`);
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

function showError(msg) {
  alert(`GenomePulse Processing Notice: ${msg}`);
}
