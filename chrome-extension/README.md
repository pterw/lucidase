# Lucidase Font Studio — Chrome Extension

A dedicated Chrome Extension (Manifest V3) that loads your Adobe Typekit typography kit (`gfe3vcu`) and provides live, instant font role switching for Lucidase and clinical applications.

---

## Features

- **Four Kit Families**: Typekit kit `gfe3vcu` exposes Akzidenz-Grotesk Next Pro (sans), Orpheus Pro (serif), Input Mono (monospace) and Swiss 721 BT Condensed (display), plus a system fallback per role.
- **Role-Based Mapping**:
  - `1. Primary UI Sans` (`--font-sans`)
  - `2. Editorial & Clinical Narrative` (`--font-serif`)
  - `3. Monospace & Genomic Figures` (`--font-mono`)
  - `4. Display & Bold Multipliers` (`--font-display`)
- **1-Click Presets**:
  - Every preset button applies the four kit families above, since the kit exposes one family per role.
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
5. The **Lucidase Font Studio** icon (`🎨`) will appear in your Chrome toolbar.
6. Click the extension icon while viewing `http://localhost:8000/` to test presets and live-swap fonts.
