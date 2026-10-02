/**
 * Font Kit Studio — Design Bridge Protocol v1 Target SDK
 * =======================================================
 * Standalone, zero-dependency bridge runtime for code-owned web applications.
 * Can be dropped into ANY web project via <script> tag or ESM import.
 *
 * Capabilities:
 *  - Two-way live visual editing between Font Kit Studio Composer and the live web page.
 *  - Live movement in wireframe setup (up and down DOM & CSS order reordering).
 *  - Seamless placement of PNG or SVG assets into target elements and containers.
 *  - Live streaming typography, text content, color, and spacing updates.
 *  - Interactive highlight overlay and bidirectional slot selection.
 *  - Zero editor chrome leakage into target DOM; clean scoped overlays.
 *
 * Specification: font-kit-studio-v0.2.0-design-bridge-protocol-v1.md
 */

(function (global) {
  'use strict';

  class FontKitBridge {
    constructor(options = {}) {
      this.protocolVersion = 1;
      this.revision = 1;
      this.sessionId = options.sessionId || `fkb-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      this.options = {
        autoDiscover: true,
        allowedOrigins: options.allowedOrigins || ['*'],
        tokens: options.tokens || {},
        enableHighlightOverlay: true,
        enableClickToSelect: true,
        onApplied: options.onApplied || null,
        ...options
      };

      this.targets = new Map();
      this.activeStudioSource = null;
      this.activeStudioOrigin = null;
      this.overlayEl = null;
      this.overlayTimer = null;

      this.init();
    }

    init() {
      if (this.options.autoDiscover) {
        this.discoverTargets();
      }

      window.addEventListener('message', (e) => this.handleMessage(e));

      // Interactive hover & click selection
      if (this.options.enableClickToSelect) {
        document.addEventListener('click', (e) => this.handleDocumentClick(e), true);
        document.addEventListener('mouseover', (e) => {
          const target = e.target.closest('[data-design-id], [data-design-role]');
          if (!target) {
            this.hideHoverOutline();
            return;
          }
          this.showHoverOutline(target);
        }, true);
        document.addEventListener('mouseleave', () => this.hideHoverOutline(), true);
      }

      // Observe dynamic DOM additions with data-design-id or data-design-role
      if (typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(() => this.discoverTargets());
        observer.observe(document.body || document.documentElement, {
          childList: true,
          subtree: true
        });
      }

      this.setupOverlay();
      this.announceReadiness();
    }

    setupOverlay() {
      if (!this.options.enableHighlightOverlay || typeof document === 'undefined') return;
      if (document.getElementById('fontkit-bridge-overlay')) return;

      const overlay = document.createElement('div');
      overlay.id = 'fontkit-bridge-overlay';
      overlay.style.cssText = `
        position: fixed;
        pointer-events: none;
        z-index: 999999;
        display: none;
        border: 2px solid #0284c7;
        box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.8), 0 0 16px rgba(2, 132, 199, 0.45);
        border-radius: 4px;
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        box-sizing: border-box;
      `;

      const badge = document.createElement('div');
      badge.id = 'fontkit-bridge-badge';
      badge.style.cssText = `
        position: absolute;
        bottom: calc(100% + 4px);
        left: -2px;
        background: #0284c7;
        color: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
        font-size: 11px;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        white-space: nowrap;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
        letter-spacing: 0.04em;
        text-transform: uppercase;
      `;
      overlay.appendChild(badge);

      // Hover Outline element
      const hoverOverlay = document.createElement('div');
      hoverOverlay.id = 'fontkit-bridge-hover';
      hoverOverlay.style.cssText = `
        position: fixed;
        pointer-events: none;
        z-index: 999998;
        display: none;
        border: 2px dashed #38bdf8;
        background: rgba(56, 189, 248, 0.08);
        border-radius: 4px;
        transition: all 0.12s ease;
        box-sizing: border-box;
      `;
      const hoverBadge = document.createElement('div');
      hoverBadge.style.cssText = `
        position: absolute;
        bottom: calc(100% + 2px);
        left: -2px;
        background: #0284c7;
        color: #ffffff;
        font-family: monospace;
        font-size: 10px;
        font-weight: 700;
        padding: 2px 6px;
        border-radius: 3px;
        white-space: nowrap;
        pointer-events: none;
      `;
      hoverOverlay.appendChild(hoverBadge);

      (document.body || document.documentElement).appendChild(overlay);
      (document.body || document.documentElement).appendChild(hoverOverlay);
      this.overlayEl = overlay;
      this.hoverOverlayEl = hoverOverlay;
      this.hoverBadgeEl = hoverBadge;
    }

    showHoverOutline(el) {
      if (!this.hoverOverlayEl || !el) return;
      const rect = el.getBoundingClientRect();
      this.hoverOverlayEl.style.display = 'block';
      this.hoverOverlayEl.style.top = `${rect.top}px`;
      this.hoverOverlayEl.style.left = `${rect.left}px`;
      this.hoverOverlayEl.style.width = `${rect.width}px`;
      this.hoverOverlayEl.style.height = `${rect.height}px`;

      const id = el.getAttribute('data-design-id') || el.id || '';
      const role = el.getAttribute('data-design-role') || 'element';
      if (this.hoverBadgeEl) {
        this.hoverBadgeEl.textContent = `⚡ Click to Edit: ${role}`;
      }
    }

    hideHoverOutline() {
      if (this.hoverOverlayEl) {
        this.hoverOverlayEl.style.display = 'none';
      }
    }

    showActiveSelection(el, name) {
      if (!this.overlayEl || !el) return;
      this.hideHoverOutline();
      const rect = el.getBoundingClientRect();
      this.overlayEl.style.display = 'block';
      this.overlayEl.style.top = `${rect.top}px`;
      this.overlayEl.style.left = `${rect.left}px`;
      this.overlayEl.style.width = `${rect.width}px`;
      this.overlayEl.style.height = `${rect.height}px`;

      const badge = document.getElementById('fontkit-bridge-badge');
      if (badge) {
        badge.textContent = `✓ Selected: ${name || 'Element'}`;
      }
    }

    announceReadiness() {
      const payload = {
        type: 'design:bridge-ready',
        protocolVersion: this.protocolVersion,
        sessionId: this.sessionId
      };

      if (window.parent && window.parent !== window) {
        window.parent.postMessage(payload, '*');
      }
      if (window.opener) {
        window.opener.postMessage(payload, '*');
      }
    }

    registerElementTarget(el, customId, customRole, customName) {
      if (!el || el.nodeType !== 1) return;
      const id = customId || el.getAttribute('data-design-id') || el.id || `design-el-${Math.random().toString(36).slice(2, 7)}`;
      const role = customRole || el.getAttribute('data-design-role') || this.inferRoleFromElement(el);
      const name = customName || el.getAttribute('data-design-name') || this.generateFriendlyName(el, role);
      const isImage = el.tagName.toLowerCase() === 'img' || el.tagName.toLowerCase() === 'svg' || role === 'image' || id.includes('mark') || id.includes('graphic') || id.includes('image');
      const computed = window.getComputedStyle(el);

      this.targets.set(id, {
        id,
        role,
        name,
        kind: isImage ? 'image' : 'text',
        element: el,
        initialText: el.textContent.trim(),
        initialHTML: el.innerHTML,
        computed: {
          fontFamily: computed.fontFamily,
          fontSize: computed.fontSize,
          fontWeight: computed.fontWeight,
          color: computed.color,
          letterSpacing: computed.letterSpacing,
          lineHeight: computed.lineHeight
        }
      });
    }

    inferRoleFromElement(el) {
      const tag = el.tagName.toLowerCase();
      const cls = (el.className || '').toString().toLowerCase();
      const id = (el.id || '').toLowerCase();

      if (tag === 'img' || tag === 'svg' || tag === 'picture' || cls.includes('logo') || cls.includes('mark') || cls.includes('icon') || id.includes('logo')) {
        return 'image';
      }
      if (cls.includes('wordmark') || cls.includes('brand') || id.includes('brand')) {
        return 'wordmark';
      }
      if (tag === 'h1' || cls.includes('hero-title') || cls.includes('display')) {
        return 'display';
      }
      if (tag === 'h2' || cls.includes('title') || cls.includes('heading')) {
        return 'title';
      }
      if (tag === 'h3' || tag === 'h4') {
        return 'subhead';
      }
      if (cls.includes('tagline') || cls.includes('deck') || cls.includes('lead') || cls.includes('editorial') || cls.includes('narrative')) {
        return 'editorial';
      }
      if (cls.includes('badge') || cls.includes('chip') || cls.includes('pill') || cls.includes('tag')) {
        return 'badge';
      }
      if (cls.includes('stat') || cls.includes('metric') || cls.includes('kpi') || cls.includes('counter')) {
        return 'stat';
      }
      if (tag === 'button' || cls.includes('btn')) {
        return 'button';
      }
      if (tag === 'p') {
        return 'body';
      }
      return 'generic';
    }

    generateFriendlyName(el, role, idx = 0) {
      const text = (el.textContent || '').trim();
      const tag = el.tagName.toUpperCase();
      if (text.length > 0 && text.length <= 25) {
        return `${tag}: "${text}"`;
      }
      if (text.length > 25) {
        return `${tag}: "${text.slice(0, 22)}…"`;
      }
      if (el.getAttribute('alt')) {
        return `Image: ${el.getAttribute('alt')}`;
      }
      return `${role.toUpperCase()} (${tag})`;
    }

    discoverTargets() {
      // 1. Explicit data-design-id elements (highest authority)
      const explicit = document.querySelectorAll('[data-design-id], [data-design-role]');
      explicit.forEach((el) => {
        this.registerElementTarget(el);
      });

      // 2. Zero-Hook Auto-Discovery: Instrument all semantic elements without requiring manual markup
      if (this.options.autoDiscoverSemantic !== false) {
        const semanticSelectors = [
          'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'header p', 'main p', 'article p', 'section p',
          'header a', 'nav a', 'button', '.btn',
          'img', 'svg', 'picture',
          '[class*="title"]', '[class*="heading"]', '[class*="brand"]', '[class*="wordmark"]', '[class*="badge"]', '[class*="stat"]'
        ];

        try {
          const autoEls = document.querySelectorAll(semanticSelectors.join(', '));
          autoEls.forEach((el, idx) => {
            if (el.closest('#fontkit-bridge-overlay, #fontkit-bridge-hover, script, style, noscript')) return;
            if (el.hasAttribute('data-design-id')) return; // already explicitly registered

            const role = this.inferRoleFromElement(el);
            const friendlyName = this.generateFriendlyName(el, role, idx);
            const autoId = `auto:${el.tagName.toLowerCase()}:${role}:${idx}`;

            el.setAttribute('data-design-id', autoId);
            el.setAttribute('data-design-role', role);
            el.setAttribute('data-design-name', friendlyName);

            this.registerElementTarget(el, autoId, role, friendlyName);
          });
        } catch (e) {}
      }
    }

    getTargetManifest() {
      this.discoverTargets();
      const manifest = [];
      for (const [id, t] of this.targets.entries()) {
        manifest.push({
          id: t.id,
          role: t.role,
          name: t.name,
          kind: t.kind,
          computed: t.computed
        });
      }
      return manifest;
    }

    getCurrentTokens() {
      const rootStyle = window.getComputedStyle(document.documentElement);
      const tokenKeys = [
        '--font-sans',
        '--font-serif',
        '--font-mono',
        '--font-display',
        '--editorial-size',
        '--mono-spacing',
        '--brand-canvas',
        '--accent-cyan',
        '--accent-emerald',
        '--accent-purple'
      ];

      const tokens = {};
      tokenKeys.forEach((key) => {
        const val = rootStyle.getPropertyValue(key).trim();
        if (val) tokens[key] = val;
      });

      return tokens;
    }

    handleMessage(event) {
      const data = event.data;
      if (!data || typeof data !== 'object' || !data.type) return;

      if (data.type.startsWith('design:') || data.type.startsWith('fontkit:')) {
        this.activeStudioSource = event.source;
        this.activeStudioOrigin = event.origin;
      }

      switch (data.type) {
        case 'design:restore-text':
          this.handleRestoreText(event.source, data);
          break;

        case 'design:hello':
          this.handleHello(event.source, data);
          break;

        case 'design:update':
          this.handleUpdate(event.source, data);
          break;

        case 'design:highlight':
          this.handleHighlight(event.source, data);
          break;

        case 'design:inspect':
          this.handleInspect(event.source, data);
          break;

        case 'design:ping':
          this.postResponse(event.source, {
            type: 'design:pong',
            revision: this.revision,
            sessionId: this.sessionId
          });
          break;

        case 'fontkit:change':
          this.handleFontKitChange(event.source, data);
          break;
      }
    }

    handleHello(source, message) {
      this.revision++;
      const response = {
        type: 'design:ready',
        protocolVersion: this.protocolVersion,
        sessionId: message.sessionId || this.sessionId,
        revision: this.revision,
        capabilities: {
          inspect: true,
          patch: true,
          assets: true,
          liveMovement: true,
          svgPlacement: true,
          pngPlacement: true,
          typography: true,
          tokens: true
        },
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight
        },
        tokens: {
          css: this.getCurrentTokens()
        },
        targets: this.getTargetManifest()
      };

      this.postResponse(source, response);
    }

    handleUpdate(source, message) {
      const patch = message.patch || {};
      const canonicalPatch = {};
      const root = document.documentElement;

      // 1. Global CSS tokens
      if (patch.tokens && typeof patch.tokens === 'object') {
        canonicalPatch.tokens = {};
        for (const [key, val] of Object.entries(patch.tokens)) {
          if (typeof val === 'string') {
            root.style.setProperty(key, val);
            canonicalPatch.tokens[key] = val;
          }
        }
      }

      // Direct token shortcuts
      ['sans', 'serif', 'mono', 'display'].forEach((role) => {
        if (patch[role]) {
          const varName = `--font-${role}`;
          root.style.setProperty(varName, patch[role]);
          canonicalPatch[varName] = patch[role];
        }
      });

      // 2. Live Movement in Wireframe Setup Up and Down (Reordering)
      if (patch.layout && Array.isArray(patch.layout.order)) {
        this.applyWireframeMovement(patch.layout.order, patch.slots);
      } else if (Array.isArray(patch.slots)) {
        this.applyWireframeMovement(patch.slots.map((s, idx) => ({ id: s.id, role: s.role, index: idx })), patch.slots);
      }

      // 3. Structured Slots Synchronization (Live text, typography, and PNG / SVG placement)
      if (Array.isArray(patch.slots)) {
        patch.slots.forEach((slot, index) => {
          this.applySlotUpdate(slot, index);
        });
      }

      // 4. Target-specific direct mutations
      if (message.targetId) {
        const targetObj = this.findTarget(message.targetId);
        if (targetObj && targetObj.element) {
          const el = targetObj.element;
          if (patch.styles) {
            Object.assign(el.style, patch.styles);
          }
          if (patch.text) {
            el.textContent = patch.text;
          }
        }
      }

      this.revision++;

      if (typeof this.options.onApplied === 'function') {
        try {
          this.options.onApplied(canonicalPatch, this.revision);
        } catch (err) {
          console.warn('[FontKitBridge] onApplied callback error:', err);
        }
      }

      this.postResponse(source, {
        type: 'design:applied',
        requestId: message.requestId || `req-${Date.now()}`,
        revision: this.revision,
        targetId: message.targetId || 'global',
        canonicalPatch
      });
    }

    /**
     * Finds target element by ID, role, or semantic match.
     */
    findTarget(idOrRole) {
      if (!idOrRole) return null;
      if (this.targets.has(idOrRole)) return this.targets.get(idOrRole);

      // Query DOM directly
      const direct = document.querySelector(`[data-design-id="${idOrRole}"]`);
      if (direct) {
        this.discoverTargets();
        return this.targets.get(idOrRole) || { element: direct, id: idOrRole };
      }

      // Search by role match
      const lower = idOrRole.toLowerCase();
      for (const [id, target] of this.targets.entries()) {
        if (target.role && target.role.toLowerCase() === lower) return target;
        if (id.toLowerCase().includes(lower)) return target;
      }

      return null;
    }

    /**
     * Live Movement in Wireframe: Handles up & down movement of sections / elements.
     */
    applyWireframeMovement(orderList, slotsList = []) {
      if (!Array.isArray(orderList)) return;

      const orderContainers = document.querySelectorAll('[data-design-order-container="true"], main, #main-content-flow');
      
      orderContainers.forEach((container) => {
        const children = Array.from(container.children);
        if (children.length <= 1) return;

        // Apply smooth transition CSS
        children.forEach((child) => {
          if (!child.style.transition) {
            child.style.transition = 'transform 0.3s cubic-bezier(0.2, 0.9, 0.3, 1), opacity 0.2s ease, order 0.25s ease';
          }
        });

        // Map order based on slot index
        orderList.forEach((item, slotIndex) => {
          const matchedEl = this.resolveElementForSlot(item, slotsList);
          if (matchedEl && container.contains(matchedEl)) {
            let containerChild = matchedEl;
            while (containerChild.parentElement && containerChild.parentElement !== container) {
              containerChild = containerChild.parentElement;
            }

            if (containerChild && containerChild.parentElement === container) {
              containerChild.style.order = slotIndex;
            }
          }
        });

        // Physical DOM reordering if ordered items share direct parent
        const rankedChildren = [];
        children.forEach((child) => {
          const rawOrder = child.style.order;
          if (rawOrder !== '') {
            rankedChildren.push({ child, order: parseInt(rawOrder, 10) });
          }
        });

        if (rankedChildren.length > 1) {
          rankedChildren.sort((a, b) => a.order - b.order);
          rankedChildren.forEach((item) => {
            container.appendChild(item.child);
          });
        }
      });

      // Dispatch layout change event
      try {
        window.dispatchEvent(new CustomEvent('design:order-changed', { detail: { order: orderList } }));
      } catch (e) {}
    }

    /**
     * Resolves matching DOM element for a given slot.
     */
    resolveElementForSlot(slot, allSlots = []) {
      if (!slot) return null;
      const role = (slot.role || '').toLowerCase();
      const type = slot.type || 'text';

      // 1. Direct targetId match (most specific for live selected elements)
      if (slot.targetId) {
        const directTarget = this.findTarget(slot.targetId);
        if (directTarget && directTarget.element) return directTarget.element;
      }

      // 2. Direct ID match
      if (slot.id && this.targets.has(slot.id)) {
        return this.targets.get(slot.id).element;
      }

      // 2. Direct data-design-id by role slug
      const slugId = role.replace(/[^a-z0-9]/g, '.');
      const directSlug = document.querySelector(`[data-design-id*="${slugId}"]`);
      if (directSlug) return directSlug;

      // 3. Image / Graphic / Mark
      if (type === 'image' || role.includes('image') || role.includes('graphic') || role.includes('mark') || role.includes('icon') || role.includes('logo')) {
        const imgTarget = document.querySelector('[data-design-id*="mark"], [data-design-id*="graphic"], [data-design-role="image"], img[data-design-id]');
        if (imgTarget) return imgTarget;
      }

      // 4. Wordmark / Brand
      if (role.includes('wordmark') || role.includes('brand')) {
        const brandEl = document.querySelector('[data-design-id*="brand.wordmark"], [data-design-id*="brand"], [data-design-role="display"]');
        if (brandEl) return brandEl;
      }

      // 5. Title / H1 / H2 / Hero / Heading / Display
      if (role === 'h1' || role === 'h2' || role.includes('title') || role.includes('hero') || role.includes('heading') || role.includes('display')) {
        const titleEl = document.querySelector('[data-design-id*="hero.title"], [data-design-id*="title"], [data-design-role="display"], h1, h2');
        if (titleEl) return titleEl;
      }

      // 6. Tagline / Editorial / Accent / Narrative / Quote
      if (role.includes('tagline') || role.includes('editorial') || role.includes('accent') || role.includes('narrative') || role.includes('quote')) {
        const narrativeEl = document.querySelector('[data-design-id*="tagline"], [data-design-id*="narrative"], [data-design-role="editorial"]');
        if (narrativeEl) return narrativeEl;
      }

      // 7. Body / Deck / Paragraph
      if (role.includes('body') || role.includes('deck') || role.includes('paragraph') || role.includes('lead')) {
        const bodyEl = document.querySelector('[data-design-id*="deck"], [data-design-role="body"], p[data-design-id]');
        if (bodyEl) return bodyEl;
      }

      // 8. Badge / Metric / Stat / Metadata
      if (role.includes('badge') || role.includes('metric') || role.includes('stat') || role.includes('metadata') || role.includes('kpi')) {
        const badgeEl = document.querySelector('[data-design-id*="stat"], [data-design-id*="badge"], [data-design-role="stat"], [data-design-role="metric"]');
        if (badgeEl) return badgeEl;
      }

      // 9. Index-based fallback across primary targets
      const primaryTargets = Array.from(document.querySelectorAll('[data-design-id]'));
      if (slot.index !== undefined && primaryTargets[slot.index]) {
        return primaryTargets[slot.index];
      }

      return null;
    }

    /**
     * Applies real-time updates for a single slot (Typography, Text, Color, or PNG / SVG placement).
     */
    applySlotUpdate(slot, index) {
      if (!slot) return;
      const el = this.resolveElementForSlot(slot);
      if (!el) return;

      // Ensure target is tracked
      if (slot.id && !this.targets.has(slot.id)) {
        this.targets.set(slot.id, { id: slot.id, role: slot.role, element: el });
      }

      // A. PNG / SVG Asset Placement
      if (slot.type === 'image') {
        this.placeAsset(el, slot);
        return;
      }

      // B. Typography & Text Content
      if (slot.type === 'text') {
        // ONLY update text content if explicitly marked as touched/edited by the user
        // This protects the application's actual content from being overwritten with preset dummy poetry
        if (slot.textTouched && slot.text !== undefined && slot.text !== null) {
          if (el.children.length === 0) {
            el.textContent = slot.text;
          } else {
            const textNode = Array.from(el.childNodes).find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0);
            if (textNode) {
              textNode.textContent = slot.text;
            } else {
              el.textContent = slot.text;
            }
          }
        }

        if (slot.fontFamily) el.style.setProperty('font-family', slot.fontFamily, 'important');
        if (slot.size) el.style.setProperty('font-size', `${slot.size}px`, 'important');
        if (slot.weight) el.style.setProperty('font-weight', String(slot.weight), 'important');
        if (slot.lineHeight) el.style.setProperty('line-height', String(slot.lineHeight), 'important');
        if (slot.tracking !== undefined) el.style.setProperty('letter-spacing', `${slot.tracking / 1000}em`, 'important');
        if (slot.colorHex) el.style.setProperty('color', slot.colorHex, 'important');
        if (slot.align) el.style.setProperty('text-align', slot.align, 'important');
        if (slot.transform) el.style.setProperty('text-transform', slot.transform, 'important');

        // Dynamically update active selection HUD bounds if this element is selected
        if (this.currentSelectedElement === el) {
          this.showActiveSelection(el, slot.role || 'Element');
        }
      }

      // C. Spacer Height
      if (slot.type === 'spacer' && slot.spacerHeight) {
        el.style.marginTop = `${slot.spacerHeight}px`;
      }

      // D. Rule Width & Thickness
      if (slot.type === 'rule') {
        if (slot.ruleWidth) el.style.width = `${slot.ruleWidth}%`;
        if (slot.ruleThickness) el.style.borderTopWidth = `${slot.ruleThickness}px`;
        if (slot.colorHex) el.style.borderColor = slot.colorHex;
      }
    }

    /**
     * Seamlessly places PNG or SVG assets into the target element or container.
     */
    placeAsset(targetContainer, slot) {
      if (!targetContainer) return;
      const dataUrl = slot.assetDataUrl;
      const width = slot.imageWidth || 180;
      const opacity = slot.opacity !== undefined ? slot.opacity : 1;

      // If targetContainer is itself an <img>
      if (targetContainer.tagName.toLowerCase() === 'img') {
        if (dataUrl) targetContainer.src = dataUrl;
        targetContainer.style.width = `${width}px`;
        targetContainer.style.opacity = opacity;
        targetContainer.style.display = 'inline-block';
        return;
      }

      // If targetContainer is an <svg>
      if (targetContainer.tagName.toLowerCase() === 'svg') {
        if (dataUrl && dataUrl.startsWith('data:image/svg+xml')) {
          try {
            const rawSvg = decodeURIComponent(dataUrl.split(',')[1]);
            const parser = new DOMParser();
            const doc = parser.parseFromString(rawSvg, 'image/svg+xml');
            const newSvg = doc.querySelector('svg');
            if (newSvg) {
              newSvg.style.width = `${width}px`;
              newSvg.style.opacity = opacity;
              targetContainer.replaceWith(newSvg);
              this.targets.set(slot.id, { id: slot.id, role: slot.role, element: newSvg });
              return;
            }
          } catch (e) {}
        }
      }

      // Container element (e.g. <div> or <figure>)
      if (dataUrl) {
        let placedImg = targetContainer.querySelector('img.fontkit-placed-asset');
        if (!placedImg) {
          placedImg = document.createElement('img');
          placedImg.className = 'fontkit-placed-asset';
          placedImg.alt = slot.imageName || 'Placed Asset';
          placedImg.style.cssText = `
            display: inline-block;
            max-width: 100%;
            height: auto;
            object-fit: contain;
            border-radius: 4px;
            transition: all 0.25s ease;
          `;
          // Clear text emoji if present
          if (targetContainer.textContent.length < 5 && /[\u{1F300}-\u{1F9FF}]/u.test(targetContainer.textContent)) {
            targetContainer.textContent = '';
          }
          targetContainer.appendChild(placedImg);
        }

        placedImg.src = dataUrl;
        placedImg.style.width = `${width}px`;
        placedImg.style.opacity = opacity;
        targetContainer.style.display = 'flex';
        targetContainer.style.alignItems = 'center';
        targetContainer.style.justifyContent = 'center';
      }
    }

    /**
     * Highlights an active slot in the target web app with an interactive HUD.
     */
    handleHighlight(source, message) {
      if (!this.overlayEl) return;
      const targetId = message.targetId;
      const slotIndex = message.slotIndex ?? 0;
      const role = message.role || 'Slot';

      let targetEl = null;
      if (targetId && this.targets.has(targetId)) {
        targetEl = this.targets.get(targetId).element;
      } else {
        targetEl = this.resolveElementForSlot({ id: targetId, role, index: slotIndex });
      }

      if (!targetEl) {
        this.overlayEl.style.display = 'none';
        return;
      }

      const rect = targetEl.getBoundingClientRect();
      this.overlayEl.style.display = 'block';
      this.overlayEl.style.top = `${rect.top}px`;
      this.overlayEl.style.left = `${rect.left}px`;
      this.overlayEl.style.width = `${rect.width}px`;
      this.overlayEl.style.height = `${rect.height}px`;

      const badge = document.getElementById('fontkit-bridge-badge');
      if (badge) {
        badge.textContent = `⚡ Live Edit: ${role} (#${slotIndex + 1})`;
      }

      if (this.overlayTimer) clearTimeout(this.overlayTimer);
      this.overlayTimer = setTimeout(() => {
        if (this.overlayEl) this.overlayEl.style.display = 'none';
      }, 3500);
    }

    handleInspect(source, message) {
      if (!message.targetId) return;
      const targetObj = this.findTarget(message.targetId);
      const el = targetObj ? targetObj.element : null;
      if (!el) {
        this.postResponse(source, {
          type: 'design:inspect-result',
          targetId: message.targetId,
          found: false
        });
        return;
      }

      const rect = el.getBoundingClientRect();
      this.postResponse(source, {
        type: 'design:inspect-result',
        targetId: message.targetId,
        found: true,
        bounds: {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
          top: rect.top,
          left: rect.left
        },
        computed: {
          fontFamily: window.getComputedStyle(el).fontFamily,
          fontSize: window.getComputedStyle(el).fontSize,
          fontWeight: window.getComputedStyle(el).fontWeight,
          color: window.getComputedStyle(el).color
        }
      });
    }

    handleFontKitChange(source, message) {
      if (message.fonts) {
        const root = document.documentElement;
        if (message.fonts.sans) root.style.setProperty('--font-sans', message.fonts.sans);
        if (message.fonts.serif) root.style.setProperty('--font-serif', message.fonts.serif);
        if (message.fonts.mono) root.style.setProperty('--font-mono', message.fonts.mono);
        if (message.fonts.display) root.style.setProperty('--font-display', message.fonts.display);
      }
      this.revision++;
      this.postResponse(source, {
        type: 'fontkit:ack',
        revision: this.revision
      });
    }

    handleDocumentClick(e) {
      const target = e.target.closest('[data-design-id], [data-design-role]');
      if (!target) return;

      // Prevent file dialogs or link clicks when selecting design elements
      e.preventDefault();
      e.stopPropagation();

      const targetId = target.getAttribute('data-design-id') || target.id;
      const role = target.getAttribute('data-design-role') || 'generic';
      const name = target.getAttribute('data-design-name') || role;
      const currentText = target.textContent.trim();
      const comp = window.getComputedStyle(target);

      this.currentSelectedElement = target;
      this.showActiveSelection(target, name);

      const msg = {
        type: 'design:select-slot',
        targetId,
        role,
        name,
        currentText,
        computed: {
          fontSize: comp.fontSize,
          fontFamily: comp.fontFamily,
          fontWeight: comp.fontWeight,
          lineHeight: comp.lineHeight,
          color: comp.color,
          letterSpacing: comp.letterSpacing,
          textAlign: comp.textAlign,
          textTransform: comp.textTransform
        }
      };

      if (window.parent && window.parent !== window) {
        window.parent.postMessage(msg, '*');
      }
      if (window.opener) {
        window.opener.postMessage(msg, '*');
      }
    }

    postResponse(targetWindow, message) {
      if (!targetWindow || !targetWindow.postMessage) return;
      try {
        targetWindow.postMessage(message, '*');
      } catch (err) {
        console.warn('[FontKitBridge] postMessage delivery failed:', err);
      }
    }
  }

  // Global factory export
  function initFontKitBridge(options) {
    if (!global.__fontkitBridge) {
      global.__fontkitBridge = new FontKitBridge(options);
    }
    return global.__fontkitBridge;
  }

  // Auto-initialize in browser
  if (typeof window !== 'undefined') {
    global.FontKitBridge = FontKitBridge;
    global.initFontKitBridge = initFontKitBridge;
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => initFontKitBridge());
    } else {
      initFontKitBridge();
    }
  }

  // CommonJS / ESM support
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { FontKitBridge, initFontKitBridge };
  }
})(typeof window !== 'undefined' ? window : globalThis);
