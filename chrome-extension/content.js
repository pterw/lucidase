/**
 * Lucidase Font Studio - Content Script
 * Automatically ensures Typekit stylesheet is loaded and listens for live updates.
 */

(function () {
  // Ensure Adobe Typekit stylesheet is injected
  if (!document.getElementById("typekit-stylesheet-ext")) {
    const link = document.createElement("link");
    link.id = "typekit-stylesheet-ext";
    link.rel = "stylesheet";
    link.href = "https://use.typekit.net/cqu4tvx.css";
    document.head.appendChild(link);
  }

  // Listen for messages from extension popup
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "UPDATE_FONTS") {
      const cfg = msg.config;
      document.documentElement.style.setProperty("--font-sans", cfg.sans);
      document.documentElement.style.setProperty("--font-serif", cfg.serif);
      document.documentElement.style.setProperty("--font-mono", cfg.mono);
      document.documentElement.style.setProperty("--font-display", cfg.display);
      sendResponse({ status: "ok" });
    } else if (msg.type === "TOGGLE_STUDIO") {
      const btn = document.getElementById("btn-font-studio");
      if (btn) {
        btn.click();
        sendResponse({ status: "toggled" });
      } else {
        sendResponse({ status: "not_found" });
      }
    }
    return true;
  });
})();
