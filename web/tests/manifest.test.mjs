import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import handler from "../api/manifest.js";

const kb = JSON.parse(readFileSync(new URL("../src/knowledge-base.json", import.meta.url), "utf-8"));

function fakeRes() {
  const res = { headers: {}, code: null, body: null };
  res.setHeader = (k, v) => { res.headers[k] = v; };
  res.status = (c) => { res.code = c; return res; };
  res.json = (b) => { res.body = b; return res; };
  res.end = () => res;
  return res;
}

test("manifest values come from knowledge-base.json, not constants", async () => {
  const res = fakeRes();
  await handler({ method: "GET" }, res);
  assert.equal(res.code, 200);
  assert.equal(res.body.sha256, kb.manifest.sha256);
  assert.equal(res.body.release_version, kb.manifest.release);
  assert.equal(res.body.variant_count, Object.keys(kb.loci).length);
});

test("manifest carries no invented upstream release claims", async () => {
  const res = fakeRes();
  await handler({ method: "GET" }, res);
  assert.equal(res.body.clinvar_release, undefined);
  assert.equal(res.body.dbsnp_build, undefined);
  assert.equal(res.body.privacy_guarantees.genomic_uploads, false);
});
