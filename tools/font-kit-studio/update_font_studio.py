import os

def update_file(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 1. Add Sync button
    old_btn = '<button id="exportCss" class="btn" type="button">Export CSS</button>'
    new_btn = '''<button id="exportCss" class="btn" type="button">Export CSS</button>
        <button id="btnSyncToApp" class="btn" type="button" style="background:#5a3aa7;color:#fff;border-color:#5a3aa7;font-weight:700;">⚡ Sync to Live App</button>'''
    if old_btn in content and 'btnSyncToApp' not in content:
        content = content.replace(old_btn, new_btn)

    # 2. Add sync function
    old_listener = 'q("exportCss").addEventListener("click", exportCompositionCss);'
    sync_code = '''q("exportCss").addEventListener("click", exportCompositionCss);

  function syncToLiveApp() {
    const tokens = {};
    state.slots.forEach(slot => {
      if (slot.type !== "text") return;
      const font = byFamily(slot.family);
      const stack = cssStack(font);
      const r = (slot.role || "").toLowerCase();
      if (r.includes("title") || r.includes("display") || r.includes("hero")) {
        tokens["--font-display"] = stack;
      } else if (r.includes("lead") || r.includes("body") || r.includes("deck")) {
        tokens["--font-sans"] = stack;
      } else if (r.includes("editorial") || r.includes("quote") || r.includes("narrative") || r.includes("serif")) {
        tokens["--font-serif"] = stack;
      } else if (r.includes("mono") || r.includes("data") || r.includes("caption") || r.includes("code")) {
        tokens["--font-mono"] = stack;
      }
    });

    if (!tokens["--font-display"] && state.slots[0]) tokens["--font-display"] = cssStack(byFamily(state.slots[0].family));
    if (!tokens["--font-sans"] && state.slots[1]) tokens["--font-sans"] = cssStack(byFamily(state.slots[1].family));
    if (!tokens["--font-serif"] && state.slots[2]) tokens["--font-serif"] = cssStack(byFamily(state.slots[2].family));
    if (!tokens["--font-mono"] && state.slots[3]) tokens["--font-mono"] = cssStack(byFamily(state.slots[3].family));

    const message = {
      type: "design:update",
      requestId: `req-${Date.now()}`,
      baseRevision: 1,
      patch: { tokens }
    };

    if (window.parent && window.parent !== window) {
      window.parent.postMessage(message, "*");
    }

    const syncBtn = document.getElementById("btnSyncToApp");
    if (syncBtn) {
      syncBtn.textContent = "✓ Synced!";
      setTimeout(() => { syncBtn.textContent = "⚡ Sync to Live App"; }, 1500);
    }
  }

  const syncBtnEl = document.getElementById("btnSyncToApp");
  if (syncBtnEl) syncBtnEl.addEventListener("click", syncToLiveApp);

  window.addEventListener("message", (event) => {
    if (event.data?.type === "design:ready") {
      console.log("[FontKitStudio] Target application connected via Design Bridge Protocol v1");
    }
  });

  if (window.parent && window.parent !== window) {
    window.parent.postMessage({ type: "design:hello", protocolVersion: 1, sessionId: "fks-" + Date.now() }, "*");
  }'''

    if old_listener in content and 'syncToLiveApp' not in content:
        content = content.replace(old_listener, sync_code)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Updated {path} successfully")

update_file(r'c:\Users\peter\Python Projects\Thing\web\font-kit-studio\font_kit_studio_v0.1.1.html')
update_file(r'c:\Users\peter\Python Projects\font kit studio\font_kit_studio_v0.1.1.html')
