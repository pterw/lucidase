/**
 * Vercel Serverless Function: Clinical Variant Enrichment with Redis Cache
 * =========================================================================
 * Endpoint: POST /api/enrich
 * Body: { rsids: ["rs429358", "rs1800562", ...] }
 *
 * Checks Upstash Redis for cached clinical data.
 * Cache hits resolve in ~3-5ms.
 * Cache misses return an offline embedded knowledge-base stub (NOT live API data).
 * Set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN to enable real caching.
 */

export default async function handler(req, res) {
  // CORS: same-origin only by default; set ALLOWED_ORIGIN env var for custom domain.
  const allowedOrigin = process.env.ALLOWED_ORIGIN || null;
  if (allowedOrigin) {
    res.setHeader("Access-Control-Allow-Origin", allowedOrigin);
    res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  }

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed. Use POST." });
  }

  const startTime = Date.now();
  const { rsids } = req.body || {};

  if (!Array.isArray(rsids) || rsids.length === 0) {
    return res.status(400).json({ error: "Invalid request. Provide an array of rsIDs in { rsids: [...] }." });
  }

  // Reject payloads that contain extraneous fields (genotypes, chromosomes, etc.)
  const allowedKeys = new Set(["rsids"]);
  for (const key of Object.keys(req.body)) {
    if (!allowedKeys.has(key)) {
      return res.status(400).json({ error: `Forbidden field '${key}'. Only 'rsids' is accepted.` });
    }
  }

  // Limit batch size to protect resources and validate format (^rs[0-9]+$)
  const MAX_BATCH = 100;
  const RSID_REGEX = /^rs\d+$/i;
  const validRsids = rsids.filter(id => typeof id === "string" && RSID_REGEX.test(id.trim()));

  if (validRsids.length === 0) {
    return res.status(400).json({ error: "No valid rsIDs provided. Expected tokens matching ^rs[0-9]+$." });
  }

  const requestedRsids = validRsids.slice(0, MAX_BATCH);

  // Check Redis configuration (Upstash REST API)
  const upstashUrl = process.env.UPSTASH_REDIS_REST_URL;
  const upstashToken = process.env.UPSTASH_REDIS_REST_TOKEN;
  const redisEnabled = Boolean(upstashUrl && upstashToken);

  let cacheHits = 0;
  let cacheMisses = 0;
  const results = {};

  if (redisEnabled) {
    try {
      // Upstash REST MGET
      const keys = requestedRsids.map(id => `variant:${id.toLowerCase()}`);
      const mgetResp = await fetch(`${upstashUrl}/mget`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${upstashToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(keys)
      });

      if (mgetResp.ok) {
        const mgetData = await mgetResp.json();
        const values = mgetData.result || [];

        const missesToFetch = [];
        keys.forEach((key, idx) => {
          const rsid = requestedRsids[idx];
          if (values[idx]) {
            try {
              results[rsid] = JSON.parse(values[idx]);
              cacheHits++;
            } catch {
              missesToFetch.push(rsid);
            }
          } else {
            missesToFetch.push(rsid);
          }
        });

        // Cache misses: return offline embedded KB stub and warm cache with TTL 30 days.
        // NOTE: This does NOT query live ClinVar/Ensembl/AlphaFold. It returns a
        // clearly-labeled offline stub. Integrate a live enrichment step here to
        // replace stubs with verified data before caching.
        if (missesToFetch.length > 0) {
          cacheMisses = missesToFetch.length;
          const pipelineCommands = [];

          for (const missId of missesToFetch) {
            const stub = buildOfflineStub(missId);
            results[missId] = stub;
            pipelineCommands.push([
              "SETEX",
              `variant:${missId.toLowerCase()}`,
              2592000,
              JSON.stringify(stub)
            ]);
          }

          // Warm cache with stubs (replace with live-enriched data when available)
          await fetch(`${upstashUrl}/pipeline`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${upstashToken}`,
              "Content-Type": "application/json"
            },
            body: JSON.stringify(pipelineCommands)
          }).catch(() => {});
        }
      } else {
        // Fallback if Redis REST failed
        requestedRsids.forEach(id => {
          results[id] = buildOfflineStub(id);
          cacheMisses++;
        });
      }
    } catch {
      requestedRsids.forEach(id => {
        results[id] = buildOfflineStub(id);
        cacheMisses++;
      });
    }
  } else {
    // Redis unconfigured: return offline stubs with setup instructions
    requestedRsids.forEach(id => {
      results[id] = buildOfflineStub(id);
    });
  }

  const durationMs = Date.now() - startTime;
  res.setHeader("X-Cache-Hits", String(cacheHits));
  res.setHeader("X-Cache-Misses", String(cacheMisses));
  res.setHeader("X-Response-Time-Ms", String(durationMs));

  return res.status(200).json({
    status: "ok",
    redis_enabled: redisEnabled,
    redis_provider: redisEnabled ? "Upstash Redis" : "None (Add UPSTASH_REDIS_REST_URL in Vercel env vars)",
    cache_hits: cacheHits,
    cache_misses: cacheMisses,
    duration_ms: durationMs,
    count: Object.keys(results).length,
    variants: results
  });
}

/**
 * Build an offline knowledge-base stub for a given rsID.
 *
 * IMPORTANT: This is NOT a live query to ClinVar, Ensembl, AlphaFold, or ENCODE.
 * Data is derived from the embedded client-side knowledge base.
 * evidence_tier is set to "embedded_kb_fallback" to distinguish from verified data.
 * No fabricated star ratings, PubMed IDs, or ACMG rationale are included.
 */
function buildOfflineStub(rsid) {
  const norm = rsid.toLowerCase();
  let gene = null;
  let uniprot = null;
  let plddt = null;
  let mode = null;
  let prior = null;

  if (norm === "rs429358" || norm === "rs7412") {
    gene = "APOE"; uniprot = "P02649"; plddt = 75.5;
    mode = "Co-Dominant Complex Alleles"; prior = 0.25;
  } else if (norm === "rs1800562" || norm === "rs1799945") {
    gene = "HFE"; uniprot = "P55899"; plddt = 86.4;
    mode = "Autosomal Recessive"; prior = 0.10;
  } else if (norm === "rs6025") {
    gene = "F5"; uniprot = "P12259"; plddt = 82.1;
    mode = "Autosomal Dominant / Incomplete Penetrance"; prior = 0.05;
  } else if (norm === "rs1799963") {
    gene = "F2"; uniprot = "P00734"; plddt = 89.2;
    mode = "Autosomal Dominant / Incomplete Penetrance"; prior = 0.02;
  } else if (norm === "rs113993960") {
    gene = "CFTR"; uniprot = "P13569"; plddt = 84.8;
    mode = "Autosomal Recessive"; prior = 0.03;
  }

  return {
    rsid,
    gene,
    evidence_tier: "embedded_kb_fallback",
    source: "offline_embedded_kb",
    note: "No live API query was performed. Data reflects the embedded client-side knowledge base only.",
    clinvar: gene ? {
      accession: null,
      stars: null,
      review_status: "not_queried"
    } : null,
    ensembl: gene ? {
      transcript: "not_queried",
      alphamissense: "not_queried",
      loeuf: null
    } : null,
    alphafold: uniprot ? {
      uniprot_id: uniprot,
      plddt,
      folding_status: "not_queried"
    } : null,
    encode: gene ? {
      tpm_expression_summary: "not_queried"
    } : null,
    segregation: mode ? {
      mode,
      carrier_prior: prior,
      risk_unscreened: Math.round(prior * 0.25 * 1000) / 1000,
      risk_carrier: 0.25
    } : null
  };
}
