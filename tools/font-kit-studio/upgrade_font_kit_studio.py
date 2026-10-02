import os

def upgrade_studio(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()

    # 1. Target Application Bridge bar
    bridge_bar = '''      <!-- Target Application Connector (Design Bridge Protocol v1) -->
      <div class="c-field span-6" style="grid-column: 1 / -1; padding: 10px 14px; background: color-mix(in srgb, var(--accent) 8%, var(--panel)); border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--line)); border-radius: 8px; margin-bottom: 6px;">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 750; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--accent);">Target Application Bridge</span>
            <span id="bridgeStatusBadge" style="font-size: 10px; padding: 2px 7px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); font-family: monospace;">Ready</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px; flex: 1; max-width: 620px;">
            <input id="targetAppUrl" type="text" value="http://localhost:8000/" placeholder="Target URL e.g. http://localhost:8000/" style="padding: 6px 10px; font-size: 12px; font-family: monospace;" />
            <button id="btnConnectTarget" class="btn" type="button" style="padding: 6px 12px; font-size: 12px; font-weight: 600;">Connect Target</button>
            <div class="segmented" style="display: inline-flex;">
              <button id="viewSpecimenCanvas" class="active" type="button" style="padding: 6px 10px; font-size: 11px;">Specimen</button>
              <button id="viewTargetApp" type="button" style="padding: 6px 10px; font-size: 11px;">Target App</button>
            </div>
          </div>
        </div>
      </div>
'''

    if 'Target Application Bridge' not in html:
        html = html.replace('<section class="composer-toolbar" aria-label="Composer setup">', '<section class="composer-toolbar" aria-label="Composer setup">\n' + bridge_bar)

    # 2. Target App Container in canvas stage
    target_container = '''        <section id="targetAppContainer" style="display: none; width: 100%; height: 720px; border-radius: 8px; overflow: hidden; border: 1px solid var(--line); background: #fff;">
          <iframe id="targetAppFrame" style="width: 100%; height: 100%; border: none;"></iframe>
        </section>'''

    if 'id="targetAppContainer"' not in html:
        html = html.replace('<section id="composerCanvas" class="composer-canvas" aria-label="Brand composition preview"></section>', '<section id="composerCanvas" class="composer-canvas" aria-label="Brand composition preview"></section>\n' + target_container)

    # 3. Target App controller script logic
    bridge_script = '''
  // ==========================================
  // Design Bridge Protocol v1 Client Logic
  // ==========================================
  const targetAppUrlInput = document.getElementById("targetAppUrl");
  const btnConnectTarget = document.getElementById("btnConnectTarget");
  const viewSpecimenBtn = document.getElementById("viewSpecimenCanvas");
  const viewTargetBtn = document.getElementById("viewTargetApp");
  const composerCanvasEl = document.getElementById("composerCanvas");
  const targetAppContainerEl = document.getElementById("targetAppContainer");
  const targetAppFrameEl = document.getElementById("targetAppFrame");
  const bridgeStatusBadge = document.getElementById("bridgeStatusBadge");

  let connectedTargetWindow = null;
  let targetRevision = 1;

  function setBridgeStatus(text, isConnected = true) {
    if (bridgeStatusBadge) {
      bridgeStatusBadge.textContent = text;
      bridgeStatusBadge.style.color = isConnected ? "var(--accent)" : "#ef4444";
      bridgeStatusBadge.style.background = isConnected ? "color-mix(in srgb, var(--accent) 15%, transparent)" : "rgba(239, 68, 68, 0.15)";
    }
  }

  function connectTargetApp(url) {
    if (!targetAppFrameEl) return;
    targetAppFrameEl.src = url || targetAppUrlInput.value || "http://localhost:8000/";
    setBridgeStatus("Connecting…", true);

    targetAppFrameEl.onload = () => {
      connectedTargetWindow = targetAppFrameEl.contentWindow;
      // Send handshake design:hello
      setTimeout(() => {
        sendDesignMessage({
          type: "design:hello",
          protocolVersion: 1,
          sessionId: "fks-" + Date.now()
        });
      }, 300);
    };
  }

  function sendDesignMessage(msg) {
    // 1. Send to hosted target iframe if active
    if (connectedTargetWindow) {
      try { connectedTargetWindow.postMessage(msg, "*"); } catch(e){}
    }
    // 2. Send to parent window if Studio is embedded
    if (window.parent && window.parent !== window) {
      try { window.parent.postMessage(msg, "*"); } catch(e){}
    }
  }

  if (btnConnectTarget) {
    btnConnectTarget.addEventListener("click", () => {
      connectTargetApp(targetAppUrlInput.value);
      switchToTargetView();
    });
  }

  function switchToSpecimenView() {
    if (viewSpecimenBtn) viewSpecimenBtn.classList.add("active");
    if (viewTargetBtn) viewTargetBtn.classList.remove("active");
    if (composerCanvasEl) composerCanvasEl.style.display = "";
    if (targetAppContainerEl) targetAppContainerEl.style.display = "none";
  }

  function switchToTargetView() {
    if (viewTargetBtn) viewTargetBtn.classList.add("active");
    if (viewSpecimenBtn) viewSpecimenBtn.classList.remove("active");
    if (composerCanvasEl) composerCanvasEl.style.display = "none";
    if (targetAppContainerEl) targetAppContainerEl.style.display = "block";
    if (!targetAppFrameEl.src || targetAppFrameEl.src === "about:blank") {
      connectTargetApp(targetAppUrlInput.value);
    }
  }

  if (viewSpecimenBtn) viewSpecimenBtn.addEventListener("click", switchToSpecimenView);
  if (viewTargetBtn) viewTargetBtn.addEventListener("click", switchToTargetView);

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || typeof data !== "object") return;

    if (data.type === "design:bridge-ready") {
      setBridgeStatus("Target Bridge Detected");
      sendDesignMessage({
        type: "design:hello",
        protocolVersion: 1,
        sessionId: "fks-" + Date.now()
      });
    } else if (data.type === "design:ready") {
      const targetCount = data.targets ? data.targets.length : 0;
      setBridgeStatus(`Connected (${targetCount} targets)`, true);
    } else if (data.type === "design:applied") {
      targetRevision = data.revision;
      setBridgeStatus(`Synced (rev ${targetRevision})`, true);
    }
  });

  // Automatically broadcast whenever slot or preset changes
  const originalApplyPreset = window.applyCompositionPreset;
'''

    if 'Design Bridge Protocol v1 Client Logic' not in html:
        html = html.replace('const rememberedComposerKits = localStorage.getItem("font-kit-studio-kit-ids");', bridge_script + '\n  const rememberedComposerKits = localStorage.getItem("font-kit-studio-kit-ids");')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Upgraded {path}")

upgrade_studio(r'c:\Users\peter\Python Projects\Thing\web\font-kit-studio\font_kit_studio_v0.1.1.html')
upgrade_studio(r'c:\Users\peter\Python Projects\font kit studio\font_kit_studio_v0.1.1.html')
