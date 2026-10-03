/**
 * The one loader for the knowledge base (web/src/knowledge-base.json), used by the worker and by the page so both
 * read the same validated KB. AGENTS.md section 3: KB validation runs at build time and again at load time.
 *
 * The KB is imported as a JSON module rather than fetched: tests/test_zero_knowledge_privacy.py requires that
 * worker.js contains no fetch call at all, and a JSON import is the same same-origin static load.
 */
import { validateKb } from "./core/kb.js";

let kbPromise = null;

/**
 * Loads and validates the knowledge base once. Rejects with a message naming the failure (a missing file, invalid
 * JSON or a schema problem). A failed load is not cached, so a retry can succeed.
 */
export function loadKnowledgeBase() {
  if (!kbPromise) {
    kbPromise = import("./knowledge-base.json", { with: { type: "json" } })
      .then((mod) => validateKb(mod.default))
      .catch((err) => {
        kbPromise = null;
        throw new Error(`The knowledge base could not be loaded: ${(err && err.message) || err}`);
      });
  }
  return kbPromise;
}
