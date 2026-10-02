/**
 * Vercel Serverless Function: Zero-Knowledge Knowledge-Base Manifest Service
 * =========================================================================
 * Endpoint: GET /api/enrich or GET /api/manifest
 *
 * Privacy Guarantees:
 * - ZERO-KNOWLEDGE: Accepts NO user genetic data, NO genotypes, NO patient IDs.
 * - Serves canonical knowledge-base release provenance, ClinVar version, and checksum.
 * - Enables clients to check for updated annotation bundles without leaking findings.
 */

const MANIFEST = {
  status: "ok",
  service: "GenomePulse Canonical Knowledge Base",
  release_version: "2026.10.02",
  release_date: "2026-10-02",
  clinvar_release: "2024-06",
  dbsnp_build: 156,
  acmg_sf_list: "ACMG Secondary Findings v3.2 (81 genes)",
  variant_count: 60,
  sha256: "e59868d4ccca9ad33fcc849a1cadc13efe2714848c1566da44fd7626832af5d3",
  zero_knowledge_certified: true,
  privacy_policy: "All primary genomic analysis is performed locally in-browser via Web Workers. No raw genotypes, rsIDs, or derived health indicators are received by this service."
};

export default async function handler(req, res) {
  // CORS: same-origin only by default; set ALLOWED_ORIGIN env var for custom domain.
  const allowedOrigin = process.env.ALLOWED_ORIGIN || null;
  if (allowedOrigin) {
    res.setHeader("Access-Control-Allow-Origin", allowedOrigin);
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  }

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  // Set immutable cache headers for edge CDN (1 hour cache, stale-while-revalidate)
  res.setHeader("Cache-Control", "public, s-maxage=3600, stale-while-revalidate=86400");
  res.setHeader("Content-Type", "application/json");

  // Always return the static release manifest
  return res.status(200).json(MANIFEST);
}
