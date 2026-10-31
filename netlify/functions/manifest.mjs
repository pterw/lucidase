/**
 * Netlify Serverless Function: Zero-Knowledge Knowledge-Base Manifest Service
 * =========================================================================
 * Endpoint: GET /api/manifest -> /.netlify/functions/manifest
 *
 * Privacy Guarantees:
 * - ZERO-KNOWLEDGE: Accepts NO user genetic data, NO genotypes, NO patient IDs.
 * - Serves the release, locus count and checksum of the shipped knowledge base.
 * - Every value is read from web/src/knowledge-base.json at request time.
 */

import { readFile } from "node:fs/promises";

export default async (req, context) => {
  const kbUrl = new URL("../../web/src/knowledge-base.json", import.meta.url);
  const kb = JSON.parse(await readFile(kbUrl, "utf-8"));
  const m = kb.manifest;

  const payload = {
    status: "ok",
    service: "Lucidase Canonical Knowledge Base",
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

  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      "Access-Control-Allow-Origin": process.env.ALLOWED_ORIGIN || "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    }
  });
};

export const config = {
  path: "/api/manifest"
};

