/**
 * Lucidase Font Studio - Extension Popup Logic
 */

// The kit gfe3vcu exposes four families (ruling 15); every preset resolves to option values that exist in the lists.
const KIT_FONTS = {
  sans: "'akzidenz-grotesk-next-pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  serif: "'orpheuspro', Georgia, serif",
  mono: "'input-mono', ui-monospace, monospace",
  display: "'swiss-721-bt-condensed', 'akzidenz-grotesk-next-pro', sans-serif"
};

const PRESETS = {
  impeccable: KIT_FONTS,
  editorial: KIT_FONTS,
  swiss: KIT_FONTS,
  cyber: KIT_FONTS
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
          if (window.__lucidase?.fontStudio) {
            window.__lucidase.fontStudio.config = {
              ...window.__lucidase.fontStudio.config,
              ...cfg
            };
            window.__lucidase.fontStudio.applyConfig();
            window.__lucidase.fontStudio.updateDropdowns();
          }
        },
        args: [config]
      });
    });
  }
});
