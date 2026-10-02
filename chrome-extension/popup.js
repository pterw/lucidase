/**
 * GenomePulse Font Studio - Extension Popup Logic
 */

const PRESETS = {
  impeccable: {
    sans: "'gotham', 'nimbus-sans', sans-serif",
    serif: "'orpheuspro', 'archer-pro', Georgia, serif",
    mono: "'attribute-mono', monospace",
    display: "'neuzeit-grotesk-condensed', 'gotham', sans-serif"
  },
  editorial: {
    sans: "'basic-sans', sans-serif",
    serif: "'mencken-std', Georgia, serif",
    mono: "'ballinger-mono', monospace",
    display: "'obviously', sans-serif"
  },
  swiss: {
    sans: "'nimbus-sans', 'gotham', sans-serif",
    serif: "'archer-pro', Georgia, serif",
    mono: "'dico-mono', monospace",
    display: "'neuzeit-grotesk-extra-conden', 'gotham', sans-serif"
  },
  cyber: {
    sans: "'century-gothic', sans-serif",
    serif: "'corporate-a', Georgia, serif",
    mono: "'azo-mono', monospace",
    display: "'dystopian', sans-serif"
  }
};

document.addEventListener("DOMContentLoaded", () => {
  const selSans = document.getElementById("select-sans");
  const selSerif = document.getElementById("select-serif");
  const selMono = document.getElementById("select-mono");
  const selDisplay = document.getElementById("select-display");
  const previewSerif = document.getElementById("preview-serif-text");
  const previewMono = document.getElementById("preview-mono-text");
  const btnApply = document.getElementById("btn-apply-tab");
  const btnToggle = document.getElementById("btn-toggle-floating");

  function getActiveConfig() {
    return {
      sans: selSans.value,
      serif: selSerif.value,
      mono: selMono.value,
      display: selDisplay.value
    };
  }

  function updatePreview() {
    previewSerif.style.fontFamily = selSerif.value;
    previewMono.style.fontFamily = selMono.value;
  }

  // Preset listeners
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const p = PRESETS[btn.getAttribute("data-preset")];
      if (p) {
        selSans.value = p.sans;
        selSerif.value = p.serif;
        selMono.value = p.mono;
        selDisplay.value = p.display;
        updatePreview();
        applyToTab(getActiveConfig());
      }
    });
  });

  [selSans, selSerif, selMono, selDisplay].forEach(sel => {
    sel.addEventListener("change", () => {
      updatePreview();
      applyToTab(getActiveConfig());
    });
  });

  if (btnApply) {
    btnApply.addEventListener("click", () => {
      applyToTab(getActiveConfig());
      btnApply.textContent = "✓ Applied!";
      setTimeout(() => { btnApply.textContent = "Apply to Page"; }, 1500);
    });
  }

  if (btnToggle) {
    btnToggle.addEventListener("click", () => {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]?.id) {
          chrome.tabs.sendMessage(tabs[0].id, { type: "TOGGLE_STUDIO" }, (res) => {
            if (chrome.runtime.lastError) {
              // Inject content script if not already present
              chrome.scripting.executeScript({
                target: { tabId: tabs[0].id },
                func: () => {
                  const btn = document.getElementById("btn-font-studio");
                  if (btn) btn.click();
                }
              });
            }
          });
        }
      });
    });
  }

  function applyToTab(config) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]?.id) return;
      chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        func: (cfg) => {
          document.documentElement.style.setProperty("--font-sans", cfg.sans);
          document.documentElement.style.setProperty("--font-serif", cfg.serif);
          document.documentElement.style.setProperty("--font-mono", cfg.mono);
          document.documentElement.style.setProperty("--font-display", cfg.display);
          // If FontStudio instance exists on window
          if (window.__genomePulse?.fontStudio) {
            window.__genomePulse.fontStudio.config = {
              ...window.__genomePulse.fontStudio.config,
              ...cfg
            };
            window.__genomePulse.fontStudio.applyConfig();
            window.__genomePulse.fontStudio.updateDropdowns();
          }
        },
        args: [config]
      });
    });
  }
});
