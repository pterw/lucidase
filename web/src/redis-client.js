/**
 * Redis Clinical Enrichment Client
 * =================================
 * Sends flagged rsIDs to the /api/enrich endpoint backed by Upstash Redis.
 * Tracks latency, cache hits, and cache misses in the UI.
 */

export class RedisEnricher {
  static async enrichVariants(rsids) {
    return this.enrichBatch(rsids);
  }

  static async enrichBatch(rsids) {
    if (!rsids || rsids.length === 0) {
      return { status: "empty", variants: {}, hits: [], misses: [], cache_hits: 0, cache_misses: 0, duration_ms: 0 };
    }

    try {
      const resp = await fetch("/api/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rsids: rsids.slice(0, 100) })
      });

      if (!resp.ok) {
        throw new Error(`Enrichment endpoint returned HTTP ${resp.status}`);
      }

      const data = await resp.json();
      return {
        ...data,
        hits: data.hits || Object.keys(data.variants || {}),
        misses: data.misses || [],
        cache_hits: data.cache_hits || (data.hits ? data.hits.length : Object.keys(data.variants || {}).length),
        cache_misses: data.cache_misses || 0
      };
    } catch (err) {
      // Local development or offline mode — no network request succeeded.
      // Return an honest stub: evidence_tier is "embedded_kb_fallback", not live-verified.
      console.warn("Redis enrichment offline fallback:", err.message);
      const stubs = rsids.slice(0, 100);
      return {
        status: "offline_stub",
        redis_enabled: false,
        hits: stubs,
        misses: [],
        cache_hits: 0,
        cache_misses: stubs.length,
        duration_ms: 0,
        variants: Object.fromEntries(stubs.map(id => [id, {
          rsid: id,
          source: "offline_embedded_kb",
          evidence_tier: "embedded_kb_fallback",
          note: "No network request was made. Clinical data is not verified from live sources."
        }]))
      };
    }
  }
}
