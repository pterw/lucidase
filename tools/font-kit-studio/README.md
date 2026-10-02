# Font Kit Studio (Developer & Design Tooling)

**Font Kit Studio** is an external visual typography composer and specimen workbench. It enables real-time visual inspection, specimen rendering, font pairing, CSS token generation, and bidirectional design synchronization over **Design Bridge Protocol v1**.

## Directory Structure
- `font_kit_studio_v0.1.1.html`: Modern flow-based typography composer and specimen studio workbench (current release).
- `font_kit_studio_v0.1.0.html`: Initial release reference.
- `fontkit-bridge.js`: Design Bridge Protocol v1 target SDK client.
- `font-kit-studio-v0.2.0-design-bridge-protocol-v1.md`: Full protocol specification.
- `update_font_studio.py` & `upgrade_font_kit_studio.py`: Automation and maintenance scripts.

## Usage
To use Font Kit Studio with GenomePulse or any web application:
1. Start your local web server (e.g. `npx serve web` or Python HTTP server on port 8788).
2. Open `font_kit_studio_v0.1.1.html` in your browser.
3. Enter your web app's URL (e.g. `http://localhost:8788`) in the Target URL composer input.
4. Interact with font specimens, typography tokens, and layout presets.
