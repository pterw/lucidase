import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(new URL("../demo-data/sample-23andme.txt", import.meta.url));

// The module is cached after the first import, so install one stub up front.
const messages = [];
globalThis.self = { postMessage: (m) => messages.push(m) };
await import("../src/worker.js");

test("worker.js parses and completes a real analysis of the demo sample", () => {
  messages.length = 0;
  assert.equal(typeof self.onmessage, "function");

  const text = readFileSync(SAMPLE, "utf8");
  self.onmessage({ data: { action: "parse", text, fileName: "sample-23andme.txt" } });

  const errors = messages.filter((m) => m.type === "error");
  assert.deepEqual(errors, []);
  const complete = messages.find((m) => m.type === "complete");
  assert.ok(complete, "worker never posted a completion message");
  assert.ok(complete.records.length >= 1, "completion carried no records");
});

test("worker.js reports a thrown failure as an error message", () => {
  messages.length = 0;
  // text that is not a string makes the parser throw
  self.onmessage({ data: { action: "parse", text: null, fileName: "x.txt" } });
  const err = messages.find((m) => m.type === "error");
  assert.ok(err, "no error message posted");
  assert.ok(typeof err.message === "string" && err.message.length > 0);
});
