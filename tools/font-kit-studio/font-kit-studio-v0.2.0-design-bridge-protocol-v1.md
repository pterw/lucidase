# Font Kit Studio v0.2.0 — Design Bridge Protocol v1

**Status:** Design freeze candidate  
**Date:** 2026-09-17  
**Scope:** v0.2.0 architecture only — no implementation yet  
**Reference target:** Asteria, used only as the first integration target. The protocol itself is application-agnostic.

---

## 1. Product Thesis

Font Kit Studio is not a page builder and not a component laboratory.

It is an **instrumented local companion workflow for code-owned applications**.

The running application remains the source of truth for layout, routing, application state, database-backed content, responsive behavior, component composition, CSS/Tailwind output, framework runtime, and final rendering.

Studio does not import the application into a visual-builder-owned rendering model. It does not scrape arbitrary selectors and reconstitute the app as utility-class blobs. Instead, the application deliberately exposes a bounded design API through stable `data-design-*` contracts and a small bridge runtime.

> **Studio does not own the page. The running application owns the page. Studio instruments it.**

This positions Studio between two common extremes:

1. **Code-to-design component workbenches** such as Storybook/Ladle, which isolate components from their real application context.
2. **Visual builders/CMS platforms** such as Plasmic/Builder.io, which introduce their own rendering/content model and deeper SDK ownership.

Studio keeps the real application live and sovereign while providing an in-context visual editing surface.

---

## 2. Core Invariants

### 2.1 Running app is rendering authority

The target application decides whether a requested design change is valid, applies it to its live runtime state, and returns the canonical result.

Studio never assumes that the value it requested is the value the application accepted.

### 2.2 Studio is persistence authority

Studio owns durable design-state persistence.

The target application does **not** independently serialize Studio's design configuration to disk. It may keep live design state in memory for rendering, but Studio writes the acknowledged canonical state to the bound composition file.

### 2.3 Explicit API contracts, never fragile DOM paths

Editable targets are addressed by stable logical identifiers such as:

```text
landing.hero.title
landing.hero.wordmark
moments.card.title
observatory.sidebar.brand
```

These identifiers survive internal DOM rewrapping and component refactors.

Studio must never persist selectors such as:

```text
body > main > section:nth-child(2) > div > h1
```

### 2.4 Editor chrome never contaminates target markup

Hover outlines, selected-element rings, labels, handles, and editor affordances are rendered in Studio's own overlay layer above the iframe.

The target application reports geometry; it does not receive editor frame markup.

### 2.5 Cross-origin isolation is intentional

Studio and the target application may run on separate localhost ports/origins.

Example:

```text
Studio:  http://localhost:4173
Target:  http://localhost:3000
```

Communication occurs only through the versioned Design Bridge protocol over `window.postMessage()`.

Studio styles must not leak into the target application and target styles must not leak into Studio.

### 2.6 Live mutation and durable persistence are separate paths

Dragging a slider must update the live target immediately without writing to disk for every intermediate value.

Persistence happens only from canonical acknowledged state, through a debounced/serialized write path.

---

## 3. High-Level Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│                          FONT KIT STUDIO                           │
│                                                                    │
│  Toolbar / assets / fonts / palettes / history / inspector         │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Target application iframe               │  │
│  │                                                              │  │
│  │    Real app · real state · real data · real components      │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│             ↑ Studio-owned hover/selection overlay ↑               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                  │                               ▲
                  │ versioned postMessage         │
                  ▼                               │
          ┌────────────────────────────────────────────┐
          │        Target DesignBridge runtime         │
          │                                            │
          │ handshake · registry · hit testing         │
          │ patches · validation · bounds reporting    │
          └────────────────────────────────────────────┘
```

Studio owns:

- iframe hosting,
- visual overlay rendering,
- inspector UI,
- font/palette/asset tooling,
- composition state,
- history/undo,
- persistence,
- local file binding,
- protocol client.

The target bridge owns:

- protocol handshake,
- editable target registry,
- target discovery,
- hit testing,
- capability reporting,
- patch validation,
- live runtime mutation,
- geometry reporting,
- protocol server behavior.

The bridge does **not** own Studio UI, file pickers, font libraries, colour pickers, undo UI, PNG/SVG asset management, or application business state unrelated to design instrumentation.

---

## 4. Framework-Agnostic Target Contract

The bridge may be authored in TypeScript and distributed as compiled ESM, but the runtime contract is DOM + JSON + `postMessage`.

A minimal target requires only stable data attributes:

```html
<h1
  data-design-id="landing.hero.title"
  data-design-role="display"
>
  Every life is a night sky.
</h1>
```

Frameworks may generate this markup however they like.

Optional framework helpers are sugar, not protocol requirements.

### 4.1 Target IDs

`data-design-id` values are logical API identifiers.

Requirements:

- unique within the active document,
- stable across internal DOM refactors,
- human-readable,
- dot-separated by convention,
- never auto-generated from DOM position,
- duplicate IDs are a bridge error.

### 4.2 Progressive capability model

A target may work at two levels.

#### Level 1 — attribute-only discovery

The bridge can infer basic editable capabilities from the live element:

- text content,
- computed font family,
- computed font size,
- font weight,
- font style,
- line height,
- letter spacing,
- text alignment,
- text colour,
- element bounds.

#### Level 2 — explicit registration

Applications may register richer schemas:

```ts
bridge.register({
  id: "landing.hero.title",
  role: "display",
  kind: "text",
  capabilities: {
    text: true,
    typography: true,
    color: true,
    alignment: true
  },
  constraints: {
    fontWeight: {
      min: 100,
      max: 900
    }
  }
});
```

Explicit registration overrides inferred capability metadata.

---

## 5. Source of Truth and State Flow

The system has two distinct authorities.

### 5.1 Target application: rendering authority

The target decides whether a patch is valid, whether a requested value must be normalized, whether a patch is rejected, and what the application actually rendered.

### 5.2 Studio: persistence authority

Studio decides what canonical design state is durable, when acknowledged state is persisted, which local composition file is bound, and how undo/redo history is represented.

### 5.3 Canonical flow

```text
Studio inspector action
        ↓
design:update { requestId, baseRevision, patch }
        ↓
Target DesignBridge
        ↓
validate / normalize / apply
        ↓
Target runtime design state
        ↓
actual target render
        ↓
design:applied { requestId, revision, canonicalPatch }
        ↓
Studio canonical state
        ↓
debounced serialized persistence
        ↓
composition.json
```

Studio may optimistically show inspector movement, but only `design:applied` state becomes canonical and persistent.

### 5.4 Rejection flow

```text
Studio
  ↓ design:update
Target
  ↓ validation fails
Studio
  ← design:rejected
```

Example:

```json
{
  "type": "design:rejected",
  "requestId": "req-42",
  "revision": 17,
  "reason": "unsupported-value",
  "detail": {
    "property": "fontWeight",
    "requested": 550,
    "allowed": [400, 500, 600]
  }
}
```

Studio restores or normalizes the inspector to the target's authoritative state.

---

## 6. Revision Model

Protocol v1 is single-editor and local-first.

It does **not** require CRDTs, multiplayer reconciliation, vector clocks, or distributed conflict resolution.

Every acknowledged runtime design state carries a monotonically increasing integer revision.

```text
current revision: 41

Studio sends:
baseRevision: 41

Target applies patch:
new revision: 42

Target acknowledges:
revision: 42

Studio persists:
revision: 42
```

If Studio sends an outdated mutation:

```text
baseRevision: 39
targetRevision: 42
```

the target returns `design:conflict`.

Each mutation includes:

```ts
interface DesignMutationMeta {
  requestId: string;
  baseRevision: number;
}
```

---

## 7. Protocol v1 Handshake

### 7.1 Initial sequence

```text
STUDIO                            TARGET
  │                                 │
  │ iframe loads                    │
  │────────────────────────────────>│
  │                                 │
  │       design:bridge-ready       │
  │<────────────────────────────────│
  │                                 │
  │ design:hello                    │
  │ protocolVersion                 │
  │ sessionId                       │
  │────────────────────────────────>│
  │                                 │
  │       design:ready              │
  │       capabilities              │
  │       revision                  │
  │       tokens                    │
  │       targets                   │
  │       viewport                  │
  │<────────────────────────────────│
```

### 7.2 `design:bridge-ready`

```ts
interface DesignBridgeReady {
  type: "design:bridge-ready";
  protocolVersion: 1;
}
```

### 7.3 `design:hello`

```ts
interface DesignHello {
  type: "design:hello";
  protocolVersion: 1;
  sessionId: string;
}
```

### 7.4 `design:ready`

```ts
interface DesignReady {
  type: "design:ready";
  protocolVersion: 1;
  sessionId: string;
  revision: number;

  capabilities: {
    inspect: boolean;
    patch: boolean;
    assets: boolean;
    typography: boolean;
    tokens: boolean;
  };

  viewport: {
    width: number;
    height: number;
  };

  tokens: DesignTokenManifest;
  targets: DesignTargetManifest[];
}
```

Studio must not expose target controls until `design:ready` succeeds.

---

## 8. Target Manifest

```ts
interface DesignTargetManifest {
  id: string;
  role?: string;
  kind: "text" | "image" | "svg" | "container" | "component";

  editable: {
    text?: boolean;
    typography?: boolean;
    color?: boolean;
    alignment?: boolean;
    spacing?: boolean;
    asset?: boolean;
    visibility?: boolean;
  };

  constraints?: DesignTargetConstraints;
}
```

Example:

```json
{
  "id": "landing.hero.title",
  "role": "display",
  "kind": "text",
  "editable": {
    "text": true,
    "typography": true,
    "color": true,
    "alignment": true
  },
  "constraints": {
    "fontFamilies": [
      "daith-vf",
      "ella-roman",
      "orpheuspro"
    ]
  }
}
```

The manifest is a permission/capability contract, not just metadata.

Studio must not present controls that the target has not exposed.

---

## 9. Live Update Messages

### 9.1 `design:update`

```ts
interface DesignUpdate {
  type: "design:update";
  requestId: string;
  baseRevision: number;
  targetId: string;
  patch: Record<string, unknown>;
}
```

### 9.2 `design:applied`

```ts
interface DesignApplied {
  type: "design:applied";
  requestId: string;
  revision: number;
  targetId: string;
  canonicalPatch: Record<string, unknown>;
}
```

If Studio requests weight 550 and the target canonicalizes to 500, Studio persists 500.

### 9.3 `design:rejected`

```ts
interface DesignRejected {
  type: "design:rejected";
  requestId: string;
  revision: number;
  targetId?: string;
  reason:
    | "unsupported-property"
    | "unsupported-value"
    | "unknown-target"
    | "revision-conflict"
    | "invalid-message";
  detail?: Record<string, unknown>;
}
```

---

## 10. Hover, Selection, and Overlay Geometry

Because Studio and the target are intentionally cross-origin, Studio cannot use `document.elementFromPoint()` inside the iframe DOM.

Hit testing belongs to the target bridge.

### 10.1 Target-side hover flow

```text
pointermove in target
        ↓
requestAnimationFrame throttle
        ↓
document.elementFromPoint(x, y)
        ↓
closest("[data-design-id]")
        ↓
target changed?
   ┌────┴────┐
   no       yes
   │         ↓
 stop   getBoundingClientRect()
             ↓
        design:hover
```

The bridge should avoid emitting repeated hover messages while the logical target ID is unchanged.

### 10.2 `design:hover`

```ts
interface DesignHover {
  type: "design:hover";
  targetId: string | null;
  rect?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}
```

### 10.3 Coordinate translation

Studio reads the iframe's own geometry:

```js
const frameRect = iframe.getBoundingClientRect();
```

and calculates:

```text
overlayLeft = frameRect.left + targetRect.x
overlayTop  = frameRect.top  + targetRect.y
```

Selection borders and hover outlines are then drawn entirely in Studio's layer.

### 10.4 Selection

Selection is explicit and sticky.

```ts
interface DesignSelected {
  type: "design:selected";
  targetId: string;
  rect: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}
```

### 10.5 Selected-target bounds updates

The target updates selected-target geometry when layout changes through `ResizeObserver`, target scroll, iframe viewport resize, and relevant application reflow.

A `MutationObserver` may be added only if required; it is not mandatory for Protocol v1.

---

## 11. Token Manifest

Protocol v1 allows applications to advertise existing design tokens rather than forcing Studio to reverse-engineer arbitrary utility classes.

```ts
interface DesignTokenManifest {
  colors?: Record<string, string>;
  fonts?: Record<string, {
    family: string;
    fallback?: string;
  }>;
  spacing?: Record<string, string>;
  radii?: Record<string, string>;
  shadows?: Record<string, string>;
  custom?: Record<string, unknown>;
}
```

Studio may supplement target-provided tokens with independent libraries such as Tailwind colour palettes, Adobe kit families, and custom user palettes.

The target's token manifest remains authoritative for application-native tokens.

---

## 12. Tailwind Boundary

Studio does not become the Tailwind compiler for the target application.

The target application continues using its real build pipeline.

Preferred:

```text
--font-display = "ella-roman"
--color-luminous = #e6c88d
hero.title.align = center
```

Avoid making the protocol depend on generated utility strings such as:

```text
tracking-[0.247829em] text-[#f0c831]
```

If a target chooses to map semantic patches into Tailwind classes internally, that is the target adapter's responsibility.

---

## 13. Local Persistence and File Binding

Local file binding is a Studio concern, not part of the target bridge protocol.

Conceptual flow:

```text
Bind composition.json
        ↓
Studio receives FileSystemFileHandle
        ↓
Studio loads canonical composition
        ↓
live edits occur through target bridge
        ↓
acknowledged Studio state changes
        ↓
debounced serialized write
        ↓
composition.json updated
```

Persistence must debounce rapid changes, serialize writes, never overlap `createWritable()` sessions, write only acknowledged canonical state, expose dirty/saving/saved/error state, preserve the latest acknowledged revision, and recover from parse/read errors without silently replacing the file.

File System Access API support is not assumed across all browsers. Protocol v1 remains usable without direct file handles through explicit import/export. This browser limitation must not leak into the Design Bridge protocol.

---

## 14. Local Recovery

Minimum recovery model:

```text
canonical state
dirty state
last acknowledged revision
last persisted revision
save in progress
save error
```

If revision 53 arrives while revision 52 is being written, Studio queues 53 and writes it only after the current write closes.

No concurrent writable streams to the same bound file.

---

## 15. Origin and Session Validation

Every protocol message must be validated against expected iframe window, expected origin, protocol version, current session ID, recognized message type, and valid message schema.

Studio must not accept a message merely because `event.data.type` resembles a bridge message.

The target likewise accepts Studio control messages only from its configured allowed origin and active session.

Origin validation is part of the bridge contract, not optional hardening.

---

## 16. Disconnect / Reconnect Semantics

Studio must handle target reloads and development HMR.

On target bridge restart:

```text
target emits design:bridge-ready
Studio starts a fresh handshake
target emits design:ready
```

The new `design:ready` snapshot replaces Studio's assumptions about live target state.

If Studio has unsaved canonical state that differs from the reloaded target, Studio must not silently overwrite either side.

Protocol v1 surfaces a reconnect state and requires one explicit resolution path:

- reapply Studio canonical state to target, or
- accept target state as canonical.

Automatic conflict policy is deferred.

---

## 17. First Reference Integration: Asteria

Asteria is the first consumer and proving ground, not the protocol's identity.

Initial candidate IDs:

```text
landing.hero.wordmark
landing.hero.title
landing.hero.lead
landing.hero.accent

moments.page.title
moments.card.title
moments.card.prose
moments.card.metadata

observatory.sidebar.brand
```

Initial target-provided tokens may map existing Asteria design variables such as:

```text
--font-display
--font-page-title
--font-card-title
--font-moment-prose
--font-metadata
--font-ui-chrome

--color-void
--color-starlight
--color-luminous
```

The Asteria adapter must remain small enough that replacing Asteria with another target does not require Studio changes.

---

## 18. Product Boundary

Studio is **not** a page builder, CMS, component-isolation workshop, DOM scraper, arbitrary CSS DevTools replacement, framework-specific React editor, or source-code rewrite engine.

Studio **is**:

> An in-context visual workbench for code-owned interfaces.

Or, more technically:

> Live design instrumentation for running applications.

---

## 19. v0.2.0 Scope

v0.2.0 should prove the bridge architecture, not attempt the final product.

Required:

1. Studio iframe host for a local target application.
2. `DesignBridge` target runtime.
3. Protocol v1 handshake.
4. Stable `data-design-id` discovery.
5. Initial target manifest.
6. Hover hit testing in target.
7. Studio-owned hover/selection overlay.
8. Target selection.
9. Typography/color/alignment patching for text targets.
10. Revisioned update → applied/rejected cycle.
11. Target-origin validation.
12. Canonical Studio state.
13. JSON composition import/export.
14. Asteria as first adapter/proving target.

Explicitly deferred:

- arbitrary localhost pages without bridge integration,
- arbitrary DOM mutation,
- nested visual layout builder,
- drag-to-reposition artboard mode,
- source-code rewriting,
- multi-user editing,
- CRDTs,
- full asset filesystem management,
- editable SVG internals,
- generic framework component-property editors,
- production deployment of the editor bridge.

---

## 20. Design Decisions Already Frozen

The following should not be reopened during v0.2.0 implementation without a concrete blocker:

- explicit bridge integration first,
- iframe + `postMessage`,
- target app remains rendering authority,
- Studio remains persistence authority,
- stable `data-design-id` logical paths,
- cross-origin separation is intentional,
- overlays render in Studio, not target markup,
- target performs hit testing,
- live mutation precedes disk persistence,
- revisioned mutations,
- acknowledged canonical state is what gets saved,
- protocol is framework-agnostic,
- TypeScript implementation is allowed but not required by consumers,
- no requirement that Studio own the target's Tailwind build,
- Asteria is the first adapter, not the architecture.

---

## 21. Implementation Gate

No v0.2.0 implementation begins until this design is reviewed and accepted.

The next step after approval is a Superpowers implementation plan that decomposes the architecture into independently testable tasks, with Protocol v1 tests treated as the first-class contract.
