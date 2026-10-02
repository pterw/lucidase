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
  variant_count: 14,
  sha256: "2bf6cffdbff070af2d7ec7d2fba714897ef48d9e52d5ee7f1e8cbbb6151ead9f",
  privacy_guarantees: {
    local_analysis: true,
    genomic_uploads: false,
    variant_identifiers_transmitted: false
  },
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
