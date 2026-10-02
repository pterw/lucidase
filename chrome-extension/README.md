# GenomePulse Font Studio — Chrome Extension

A dedicated Chrome Extension (Manifest V3) that loads your Adobe Typekit typography kit (`cqu4tvx`) and provides live, instant font role switching for GenomePulse and clinical applications.

---

## Features

- **27 Curated Foundry Fonts**: Instantly switch between Gotham, Orpheus Pro, Attribute Mono, Neuzeit Grotesk, Mencken Std, Archer Pro, Obviously, and more.
- **Role-Based Mapping**:
  - `1. Primary UI Sans` (`--font-sans`)
  - `2. Editorial & Clinical Narrative` (`--font-serif`)
  - `3. Monospace & Genomic Figures` (`--font-mono`)
  - `4. Display & Bold Multipliers` (`--font-display`)
- **1-Click Presets**:
  - 🧬 **Impeccable Clinical**: Gotham + Orpheus Pro + Attribute Mono + Neuzeit Condensed
  - 📰 **Editorial Heavyweight**: Basic Sans + Mencken Std + Ballinger Mono + Obviously
  - 🔬 **Swiss Bio Precision**: Nimbus Sans + Archer Pro + Dico Mono + Neuzeit Extra Cond
  - ⚡ **Biotech Cyber HUD**: Century Gothic + Corporate A + Azo Mono + Dystopian
- **Zero Configuration**: Connects automatically to `http://localhost:8000/` or any web page.

---

## How to Install in Chrome

1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** using the toggle switch in the top-right corner.
3. Click the **Load unpacked** button in the top-left corner.
4. Select the directory:
   ```
   c:\Users\peter\Python Projects\Thing\chrome-extension
   ```
5. The **GenomePulse Font Studio** icon (`🎨`) will appear in your Chrome toolbar.
6. Click the extension icon while viewing `http://localhost:8000/` to test presets and live-swap fonts.
