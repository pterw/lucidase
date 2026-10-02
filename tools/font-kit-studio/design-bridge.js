/**
 * GenomePulse - Design Bridge Protocol v1 Runtime
 * ================================================
 * Implements the Design Bridge Protocol v1 for bidirectional communication
 * between Font Kit Studio (host or iframe) and GenomePulse.
 *
 * Authoritative for target rendering, capability reporting,
 * and live CSS variable / typography patching.
 */

export class DesignBridge {
  constructor() {
    this.protocolVersion = 1;
    this.revision = 1;
    this.sessionId = `gp-session-${Date.now()}`;
    this.targets = this.discoverTargets();
    this.init();
  }

  init() {
    window.addEventListener("message", (event) => this.onMessage(event));

    // Announce bridge readiness if loaded within an iframe
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({
        type: "design:bridge-ready",
        protocolVersion: this.protocolVersion
      }, "*");
    }
  }

  discoverTargets() {
    const targets = [];
    const elements = document.querySelectorAll("[data-design-id]");
    elements.forEach((el) => {
      targets.push({
        id: el.getAttribute("data-design-id"),
        role: el.getAttribute("data-design-role") || "generic",
        kind: "text",
        editable: {
          typography: true,
          color: true,
          text: true
        }
      });
    });
    return targets;
  }

  onMessage(event) {
    const data = event.data;
    if (!data || typeof data !== "object") return;

    switch (data.type) {
      case "design:hello":
        this.handleHello(event.source, data);
        break;
      case "design:update":
        this.handleUpdate(event.source, data);
        break;
      case "fontkit:change":
        this.handleFontkitChange(event.source, data);
        break;
      case "design:ping":
        if (event.source?.postMessage) {
          event.source.postMessage({ type: "design:pong", revision: this.revision }, "*");
        }
        break;
    }
  }

  handleHello(source, message) {
    this.revision++;
    const tokens = {
      "--font-sans": getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim(),
      "--font-serif": getComputedStyle(document.documentElement).getPropertyValue("--font-serif").trim(),
      "--font-mono": getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim(),
      "--font-display": getComputedStyle(document.documentElement).getPropertyValue("--font-display").trim(),
      "--editorial-size": getComputedStyle(document.documentElement).getPropertyValue("--editorial-size").trim(),
      "--mono-spacing": getComputedStyle(document.documentElement).getPropertyValue("--mono-spacing").trim()
    };

    const response = {
      type: "design:ready",
      protocolVersion: this.protocolVersion,
      sessionId: message.sessionId || this.sessionId,
      revision: this.revision,
      capabilities: {
        inspect: true,
        patch: true,
        assets: false,
        typography: true,
        tokens: true
      },
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight
      },
      tokens: {
        css: tokens
      },
      targets: this.discoverTargets()
    };

    if (source?.postMessage) {
      source.postMessage(response, "*");
    }
  }

  handleUpdate(source, message) {
    const patch = message.patch || {};
    const root = document.documentElement;
    const appliedTokens = {};

    // Apply tokens directly if supplied
    if (patch.tokens) {
      for (const [key, val] of Object.entries(patch.tokens)) {
        if (typeof val === "string") {
          root.style.setProperty(key, val);
          appliedTokens[key] = val;
        }
      }
    }

    // Apply direct CSS variables from patch
    if (patch.sans) {
      root.style.setProperty("--font-sans", patch.sans);
      appliedTokens["--font-sans"] = patch.sans;
    }
    if (patch.serif) {
      root.style.setProperty("--font-serif", patch.serif);
      appliedTokens["--font-serif"] = patch.serif;
    }
    if (patch.mono) {
      root.style.setProperty("--font-mono", patch.mono);
      appliedTokens["--font-mono"] = patch.mono;
    }
    if (patch.display) {
      root.style.setProperty("--font-display", patch.display);
      appliedTokens["--font-display"] = patch.display;
    }

    // Target-specific mutation if targeted by data-design-id
    if (message.targetId) {
      const el = document.querySelector(`[data-design-id="${message.targetId}"]`);
      if (el) {
        if (patch.fontFamily) el.style.fontFamily = patch.fontFamily;
        if (patch.fontSize) el.style.fontSize = patch.fontSize;
        if (patch.fontWeight) el.style.fontWeight = patch.fontWeight;
        if (patch.color) el.style.color = patch.color;
        if (patch.letterSpacing) el.style.letterSpacing = patch.letterSpacing;
      }
    }

    this.revision++;

    // Acknowledge update with design:applied
    if (source?.postMessage) {
      source.postMessage({
        type: "design:applied",
        requestId: message.requestId || `req-${Date.now()}`,
        revision: this.revision,
        targetId: message.targetId || "global",
        canonicalPatch: appliedTokens
      }, "*");
    }

    // Synchronize in-page fontStudio if present
    if (window.__genomePulse?.fontStudio) {
      window.__genomePulse.fontStudio.config = {
        ...window.__genomePulse.fontStudio.config,
        sans: appliedTokens["--font-sans"] || window.__genomePulse.fontStudio.config.sans,
        serif: appliedTokens["--font-serif"] || window.__genomePulse.fontStudio.config.serif,
        mono: appliedTokens["--font-mono"] || window.__genomePulse.fontStudio.config.mono,
        display: appliedTokens["--font-display"] || window.__genomePulse.fontStudio.config.display
      };
      window.__genomePulse.fontStudio.updateDropdowns();
    }
  }

  handleFontkitChange(source, message) {
    if (message.fonts) {
      const root = document.documentElement;
      if (message.fonts.sans) root.style.setProperty("--font-sans", message.fonts.sans);
      if (message.fonts.serif) root.style.setProperty("--font-serif", message.fonts.serif);
      if (message.fonts.mono) root.style.setProperty("--font-mono", message.fonts.mono);
      if (message.fonts.display) root.style.setProperty("--font-display", message.fonts.display);
    }
    this.revision++;
    if (source?.postMessage) {
      source.postMessage({ type: "fontkit:ack", revision: this.revision }, "*");
    }
  }
}
