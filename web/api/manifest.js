/**
 * Vercel Serverless Function: Zero-Knowledge Knowledge-Base Manifest Service
 * =========================================================================
 * Endpoint: GET /api/manifest
 *
 * Privacy Guarantees:
 * - ZERO-KNOWLEDGE: Accepts NO user genetic data, NO genotypes, NO patient IDs.
 * - Serves the release, locus count and checksum of the shipped knowledge base.
 * - Every value is read from src/knowledge-base.json at request time. Nothing is hard-coded here,
 *   so the manifest cannot drift from the file the app loads.
 */

import { readFile } from "node:fs/promises";

const KB_URL = new URL("../src/knowledge-base.json", import.meta.url);

async function buildManifest() {
  const kb = JSON.parse(await readFile(KB_URL, "utf-8"));
  const m = kb.manifest;
  return {
    status: "ok",
    service: "GenomePulse Canonical Knowledge Base",
    release_version: m.release,
    variant_count: m.locus_count,
    sha256: m.sha256,
    privacy_guarantees: {
      local_analysis: true,
      genomic_uploads: false,
      variant_identifiers_transmitted: false
    },
    privacy_policy: "All primary genomic analysis is performed locally in-browser via Web Workers. No raw genotypes, rsIDs, or derived health indicators are received by this service."
  };
}

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

  res.setHeader("Cache-Control", "public, s-maxage=3600, stale-while-revalidate=86400");
  res.setHeader("Content-Type", "application/json");

  return res.status(200).json(await buildManifest());
}
