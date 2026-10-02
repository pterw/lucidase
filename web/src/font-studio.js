/**
 * GenomePulse - Interactive Typography Studio
 * ============================================
 * Live font exploration and dynamic typography customization engine.
 * Powered by Adobe Typekit Kit (cqu4tvx) and custom web font loaders.
 * Real-time updates CSS custom variables across the entire application.
 */

export const TYPEKIT_CATALOG = {
  sans: [
    { id: "gotham", name: "Gotham (Geometric Clinical Sans)", stack: "'gotham', 'nimbus-sans', sans-serif" },
    { id: "nimbus-sans", name: "Nimbus Sans (Swiss Modernist)", stack: "'nimbus-sans', 'gotham', sans-serif" },
    { id: "basic-sans", name: "Basic Sans (Humanist Clean)", stack: "'basic-sans', sans-serif" },
    { id: "century-gothic", name: "Century Gothic (High-Aperture)", stack: "'century-gothic', sans-serif" },
    { id: "plau", name: "Plau (Rounded Tech Sans)", stack: "'plau', sans-serif" },
    { id: "system-sans", name: "System Sans (Native OS)", stack: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }
  ],
  editorial: [
    { id: "orpheuspro", name: "Orpheus Pro (Humanist Editorial Serif)", stack: "'orpheuspro', 'archer-pro', Georgia, serif" },
    { id: "archer-pro", name: "Archer Pro (Slab Serif Precision)", stack: "'archer-pro', Georgia, serif" },
    { id: "corporate-a", name: "Corporate A (Classical Authority)", stack: "'corporate-a', Georgia, serif" },
    { id: "mencken-std", name: "Mencken Std (Editorial Journal)", stack: "'mencken-std', Georgia, serif" },
    { id: "mencken-std-head", name: "Mencken Std Head (Editorial Display)", stack: "'mencken-std-head', Georgia, serif" },
    { id: "ella-roman", name: "Ella Roman (Refined Literary)", stack: "'ella-roman', Georgia, serif" },
    { id: "quador", name: "Quador (Contemporary Modern Serif)", stack: "'quador', Georgia, serif" },
    { id: "georgia", name: "Georgia (System Serif)", stack: "Georgia, serif" }
  ],
  mono: [
    { id: "attribute-mono", name: "Attribute Mono (Surgical Lab Monospace)", stack: "'attribute-mono', monospace" },
    { id: "ballinger-mono", name: "Ballinger Mono (Dense Data Monospace)", stack: "'ballinger-mono', monospace" },
    { id: "azo-mono", name: "Azo Mono (Geometric Technical)", stack: "'azo-mono', monospace" },
    { id: "dico-mono", name: "Dico Mono (Engineered Code)", stack: "'dico-mono', monospace" },
    { id: "anonymous-pro", name: "Anonymous Pro (Fixed-Width Classic)", stack: "'anonymous-pro', monospace" },
    { id: "prestige-elite-std", name: "Prestige Elite Std (Retro Clinical)", stack: "'prestige-elite-std', monospace" },
    { id: "system-mono", name: "System Monospace", stack: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }
  ],
  display: [
    { id: "neuzeit-grotesk-condensed", name: "Neuzeit Grotesk Condensed (High-Impact Heavy)", stack: "'neuzeit-grotesk-condensed', 'gotham', sans-serif" },
    { id: "neuzeit-grotesk-extra-conden", name: "Neuzeit Grotesk Extra Condensed", stack: "'neuzeit-grotesk-extra-conden', 'gotham', sans-serif" },
    { id: "obviously", name: "Obviously (Ultra-Expressive Display)", stack: "'obviously', sans-serif" },
    { id: "poster-gothic-atf", name: "Poster Gothic ATF (Bold Architectural)", stack: "'poster-gothic-atf', sans-serif" },
    { id: "cofo-cinema1909", name: "CoFo Cinema 1909 (Art Deco Editorial)", stack: "'cofo-cinema1909', sans-serif" },
    { id: "dystopian", name: "Dystopian (Futuristic Biotech)", stack: "'dystopian', sans-serif" },
    { id: "daith-vf", name: "Daith Variable (Dynamic Weight)", stack: "'daith-vf', sans-serif" },
    { id: "ella-brutalist", name: "Ella Brutalist (Sharp Experimental)", stack: "'ella-brutalist', sans-serif" }
  ]
};

export const PRESETS = [
  {
    id: "impeccable",
    name: "🧬 Impeccable Clinical (Default)",
    description: "Gotham + Orpheus Pro + Attribute Mono + Neuzeit Grotesk",
    sans: "'gotham', 'nimbus-sans', sans-serif",
    serif: "'orpheuspro', 'archer-pro', Georgia, serif",
    mono: "'attribute-mono', 'ballinger-mono', monospace",
    display: "'neuzeit-grotesk-condensed', 'gotham', sans-serif",
    editorialSize: "14.5px",
    monoSpacing: "0em"
  },
  {
    id: "editorial",
    name: "📰 Editorial Heavyweight",
    description: "Basic Sans + Mencken Std + Ballinger Mono + Obviously",
    sans: "'basic-sans', sans-serif",
    serif: "'mencken-std', 'mencken-std-head', Georgia, serif",
    mono: "'ballinger-mono', monospace",
    display: "'obviously', sans-serif",
    editorialSize: "15px",
    monoSpacing: "-0.01em"
  },
  {
    id: "swiss",
    name: "🔬 Swiss Bio Precision",
    description: "Nimbus Sans + Archer Pro + Dico Mono + Neuzeit Extra Cond",
    sans: "'nimbus-sans', sans-serif",
    serif: "'archer-pro', Georgia, serif",
    mono: "'dico-mono', monospace",
    display: "'neuzeit-grotesk-extra-conden', sans-serif",
    editorialSize: "14px",
    monoSpacing: "0.02em"
  },
  {
    id: "cyber",
    name: "⚡ Biotech Cyber HUD",
    description: "Century Gothic + Corporate A + Azo Mono + Dystopian",
    sans: "'century-gothic', sans-serif",
    serif: "'corporate-a', Georgia, serif",
    mono: "'azo-mono', monospace",
    display: "'dystopian', sans-serif",
    editorialSize: "15px",
    monoSpacing: "0.04em"
  }
];

export class FontStudio {
  constructor() {
    this.config = this.loadConfig();
    this.isOpen = false;
    this.init();
  }

  loadConfig() {
    try {
      const saved = localStorage.getItem("genomepulse-font-studio");
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (e) {
      console.warn("Failed to load saved font studio config:", e);
    }
    return { ...PRESETS[0] };
  }

  saveConfig() {
    try {
      localStorage.setItem("genomepulse-font-studio", JSON.stringify(this.config));
    } catch (e) {
      console.warn("Failed to save font studio config:", e);
    }
  }

  init() {
    this.applyConfig();
    this.renderUI();
    this.attachEvents();
  }

  applyConfig() {
    const root = document.documentElement;
    root.style.setProperty("--font-sans", this.config.sans);
    root.style.setProperty("--font-serif", this.config.serif);
    root.style.setProperty("--font-mono", this.config.mono);
    root.style.setProperty("--font-display", this.config.display);
    if (this.config.editorialSize) {
      root.style.setProperty("--editorial-size", this.config.editorialSize);
    }
    if (this.config.monoSpacing) {
      root.style.setProperty("--mono-spacing", this.config.monoSpacing);
    }
    this.saveConfig();
  }

  renderUI() {
    // Avoid double rendering
    if (document.getElementById("font-studio-panel")) return;

    const panel = document.createElement("div");
    panel.id = "font-studio-panel";
    panel.className = "fixed bottom-5 right-5 z-50 w-96 max-w-[calc(100vw-2rem)] max-h-[85vh] overflow-y-auto glass-panel p-5 rounded-sm shadow-2xl border-2 border-sky-500/40 hidden bg-white dark:bg-slate-900/95 transition-all duration-200";

    panel.innerHTML = `
      <div class="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
        <div class="flex items-center space-x-2">
          <span class="text-xl">🎨</span>
          <div>
            <h3 class="text-sm font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono">Font Studio</h3>
            <p class="text-[11px] text-slate-500 dark:text-slate-400">Live Adobe Typekit Typography Engine</p>
          </div>
        </div>
        <button id="font-studio-close" class="btn btn-xs btn-ghost text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 rounded-sm">✕</button>
      </div>

      <!-- Presets Selector -->
      <div class="mt-4 space-y-1.5">
        <label class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">Impeccable Presets</label>
        <div class="grid grid-cols-2 gap-1.5">
          ${PRESETS.map(p => `
            <button type="button" data-preset="${p.id}" class="preset-btn btn btn-xs btn-outline border-slate-300 dark:border-slate-700 hover:border-sky-500 text-[11px] rounded-sm justify-start font-mono text-left px-2 py-1 truncate">
              ${p.name.split(' ')[0]} ${p.name.split(' ')[1]}
            </button>
          `).join("")}
        </div>
      </div>

      <!-- Role 1: Primary Interface Sans -->
      <div class="mt-4 space-y-1.5">
        <div class="flex items-center justify-between">
          <label for="fs-select-sans" class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">1. UI & Interface Sans</label>
          <span class="text-[10px] text-sky-600 dark:text-sky-400 font-mono">--font-sans</span>
        </div>
        <select id="fs-select-sans" class="select select-bordered select-xs w-full rounded-sm text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border-slate-300 dark:border-slate-700">
          ${TYPEKIT_CATALOG.sans.map(f => `
            <option value="${f.stack}" ${this.config.sans.includes(f.id) ? "selected" : ""}>${f.name}</option>
          `).join("")}
        </select>
      </div>

      <!-- Role 2: Editorial & Clinical Narrative -->
      <div class="mt-3.5 space-y-1.5">
        <div class="flex items-center justify-between">
          <label for="fs-select-serif" class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">2. Editorial & Clinical Serif</label>
          <span class="text-[10px] text-purple-600 dark:text-purple-400 font-mono">--font-serif</span>
        </div>
        <select id="fs-select-serif" class="select select-bordered select-xs w-full rounded-sm text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border-slate-300 dark:border-slate-700">
          ${TYPEKIT_CATALOG.editorial.map(f => `
            <option value="${f.stack}" ${this.config.serif.includes(f.id) ? "selected" : ""}>${f.name}</option>
          `).join("")}
        </select>
        <div class="flex items-center justify-between pt-1">
          <span class="text-[10px] text-slate-500">Narrative Size:</span>
          <span id="fs-editorial-size-val" class="text-[10px] font-mono text-slate-700 dark:text-slate-300">${this.config.editorialSize || "14.5px"}</span>
        </div>
        <input id="fs-slider-size" type="range" min="12" max="20" step="0.5" value="${parseFloat(this.config.editorialSize) || 14.5}" class="range range-xs range-primary" />
      </div>

      <!-- Role 3: Monospace Genomic Figures -->
      <div class="mt-3.5 space-y-1.5">
        <div class="flex items-center justify-between">
          <label for="fs-select-mono" class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">3. Monospace & Genomic Data</label>
          <span class="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">--font-mono</span>
        </div>
        <select id="fs-select-mono" class="select select-bordered select-xs w-full rounded-sm text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border-slate-300 dark:border-slate-700">
          ${TYPEKIT_CATALOG.mono.map(f => `
            <option value="${f.stack}" ${this.config.mono.includes(f.id) ? "selected" : ""}>${f.name}</option>
          `).join("")}
        </select>
        <div class="flex items-center justify-between pt-1">
          <span class="text-[10px] text-slate-500">Letter Spacing:</span>
          <span id="fs-mono-spacing-val" class="text-[10px] font-mono text-slate-700 dark:text-slate-300">${this.config.monoSpacing || "0em"}</span>
        </div>
        <input id="fs-slider-spacing" type="range" min="-0.05" max="0.1" step="0.01" value="${parseFloat(this.config.monoSpacing) || 0}" class="range range-xs range-secondary" />
      </div>

      <!-- Role 4: Display & High-Density Metrics -->
      <div class="mt-3.5 space-y-1.5">
        <div class="flex items-center justify-between">
          <label for="fs-select-display" class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">4. Display Headings & Multipliers</label>
          <span class="text-[10px] text-amber-600 dark:text-amber-400 font-mono">--font-display</span>
        </div>
        <select id="fs-select-display" class="select select-bordered select-xs w-full rounded-sm text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border-slate-300 dark:border-slate-700">
          ${TYPEKIT_CATALOG.display.map(f => `
            <option value="${f.stack}" ${this.config.display.includes(f.id) ? "selected" : ""}>${f.name}</option>
          `).join("")}
        </select>
      </div>

      <!-- Live Typekit Kit Link / Project ID -->
      <div class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 space-y-1.5">
        <label for="fs-kit-url" class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-mono">Adobe Typekit Kit URL</label>
        <div class="flex space-x-1.5">
          <input id="fs-kit-url" type="text" value="https://use.typekit.net/cqu4tvx.css" class="input input-xs input-bordered w-full rounded-sm text-[11px] font-mono bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300" />
          <button id="fs-load-kit-btn" class="btn btn-xs btn-outline rounded-sm border-slate-300 dark:border-slate-700 text-xs">Load</button>
        </div>
      </div>

      <!-- Live Preview Sentence Box -->
      <div class="mt-3.5 p-2.5 rounded-sm bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1">
        <div class="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Live Preview</div>
        <p class="font-serif italic text-xs text-slate-800 dark:text-slate-200">"APOE ε4/ε4 Homozygote confers ~12–15× increased risk."</p>
        <div class="font-mono text-[11px] text-emerald-600 dark:text-emerald-400">rs429358:C>T · chr19:45411941 · 3.2ms</div>
      </div>

      <!-- Action Buttons -->
      <div class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <button id="fs-reset-btn" class="btn btn-xs btn-ghost text-slate-500 rounded-sm text-[11px]">↺ Reset</button>
        <button id="fs-copy-css" class="btn btn-xs btn-primary rounded-sm text-[11px] font-mono">📋 Copy CSS</button>
      </div>
    `;

    document.body.appendChild(panel);
  }

  attachEvents() {
    const btnToggle = document.getElementById("btn-font-studio");
    const panel = document.getElementById("font-studio-panel");
    const btnClose = document.getElementById("font-studio-close");

    if (btnToggle && panel) {
      btnToggle.addEventListener("click", () => {
        this.toggle();
      });
    }

    if (btnClose && panel) {
      btnClose.addEventListener("click", () => {
        this.close();
      });
    }

    // Role Dropdown Changes
    const selSans = document.getElementById("fs-select-sans");
    if (selSans) {
      selSans.addEventListener("change", (e) => {
        this.config.sans = e.target.value;
        this.applyConfig();
      });
    }

    const selSerif = document.getElementById("fs-select-serif");
    if (selSerif) {
      selSerif.addEventListener("change", (e) => {
        this.config.serif = e.target.value;
        this.applyConfig();
      });
    }

    const selMono = document.getElementById("fs-select-mono");
    if (selMono) {
      selMono.addEventListener("change", (e) => {
        this.config.mono = e.target.value;
        this.applyConfig();
      });
    }

    const selDisplay = document.getElementById("fs-select-display");
    if (selDisplay) {
      selDisplay.addEventListener("change", (e) => {
        this.config.display = e.target.value;
        this.applyConfig();
      });
    }

    // Sliders
    const sliderSize = document.getElementById("fs-slider-size");
    const valSize = document.getElementById("fs-editorial-size-val");
    if (sliderSize && valSize) {
      sliderSize.addEventListener("input", (e) => {
        const val = `${e.target.value}px`;
        valSize.textContent = val;
        this.config.editorialSize = val;
        this.applyConfig();
      });
    }

    const sliderSpacing = document.getElementById("fs-slider-spacing");
    const valSpacing = document.getElementById("fs-mono-spacing-val");
    if (sliderSpacing && valSpacing) {
      sliderSpacing.addEventListener("input", (e) => {
        const val = `${e.target.value}em`;
        valSpacing.textContent = val;
        this.config.monoSpacing = val;
        this.applyConfig();
      });
    }

    // Preset Buttons
    document.querySelectorAll(".preset-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const presetId = e.currentTarget.getAttribute("data-preset");
        const preset = PRESETS.find(p => p.id === presetId);
        if (preset) {
          this.applyPreset(preset);
        }
      });
    });

    // Copy CSS Button
    const btnCopyCss = document.getElementById("fs-copy-css");
    if (btnCopyCss) {
      btnCopyCss.addEventListener("click", () => {
        const css = `:root {\n  --font-sans: ${this.config.sans};\n  --font-serif: ${this.config.serif};\n  --font-mono: ${this.config.mono};\n  --font-display: ${this.config.display};\n  --editorial-size: ${this.config.editorialSize};\n  --mono-spacing: ${this.config.monoSpacing};\n}`;
        navigator.clipboard.writeText(css).then(() => {
          btnCopyCss.textContent = "✓ Copied!";
          setTimeout(() => { btnCopyCss.textContent = "📋 Copy CSS"; }, 2000);
        }).catch(() => {
          alert(css);
        });
      });
    }

    // Reset Defaults
    const btnReset = document.getElementById("fs-reset-btn");
    if (btnReset) {
      btnReset.addEventListener("click", () => {
        this.applyPreset(PRESETS[0]);
      });
    }

    // Load External Kit URL
    const btnLoadKit = document.getElementById("fs-load-kit-btn");
    const inputKitUrl = document.getElementById("fs-kit-url");
    if (btnLoadKit && inputKitUrl) {
      btnLoadKit.addEventListener("click", () => {
        const url = inputKitUrl.value.trim();
        if (url) {
          let link = document.getElementById("typekit-stylesheet");
          if (!link) {
            link = document.createElement("link");
            link.id = "typekit-stylesheet";
            link.rel = "stylesheet";
            document.head.appendChild(link);
          }
          link.href = url;
          btnLoadKit.textContent = "✓ Loaded";
          setTimeout(() => { btnLoadKit.textContent = "Load"; }, 2000);
        }
      });
    }
  }

  applyPreset(preset) {
    this.config = {
      ...this.config,
      sans: preset.sans,
      serif: preset.serif,
      mono: preset.mono,
      display: preset.display,
      editorialSize: preset.editorialSize,
      monoSpacing: preset.monoSpacing
    };
    this.applyConfig();
    this.updateDropdowns();
  }

  updateDropdowns() {
    const selSans = document.getElementById("fs-select-sans");
    if (selSans) selSans.value = this.config.sans;

    const selSerif = document.getElementById("fs-select-serif");
    if (selSerif) selSerif.value = this.config.serif;

    const selMono = document.getElementById("fs-select-mono");
    if (selMono) selMono.value = this.config.mono;

    const selDisplay = document.getElementById("fs-select-display");
    if (selDisplay) selDisplay.value = this.config.display;
  }

  toggle() {
    const panel = document.getElementById("font-studio-panel");
    if (!panel) return;
    this.isOpen = !this.isOpen;
    if (this.isOpen) {
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  }

  open() {
    const panel = document.getElementById("font-studio-panel");
    if (!panel) return;
    this.isOpen = true;
    panel.classList.remove("hidden");
  }

  close() {
    const panel = document.getElementById("font-studio-panel");
    if (!panel) return;
    this.isOpen = false;
    panel.classList.add("hidden");
  }
}
