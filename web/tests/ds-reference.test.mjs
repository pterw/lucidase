import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";

// The app's working copies of the design system (web/src/ds) against the reference copy
// (docs/design-system). The only differences allowed are the ones web/src/ds/README.md records.

const APP = new URL("../src/ds/", import.meta.url);
const REF = new URL("../../docs/design-system/", import.meta.url);
const read = (url) => readFileSync(url, "utf8").replace(/\r\n/g, "\n");

const cssNames = readdirSync(APP)
  .filter((f) => f.endsWith(".css"))
  .sort();

test("the app has the token files it is expected to have", () => {
  assert.deepEqual(cssNames, ["base.css", "colors.css", "motion.css", "shape.css", "spacing.css", "typography.css"]);
});

for (const name of cssNames) {
  test(`ds/${name} is a verbatim copy of tokens/${name}`, () => {
    const twin = new URL(`tokens/${name}`, REF);
    assert.ok(existsSync(twin), `ds/${name} has no reference twin at docs/design-system/tokens/${name}`);
    assert.equal(read(new URL(name, APP)), read(twin));
  });
}

test("the only reference token file the app does not copy is fonts.css (README: it @imports the Adobe Fonts kit)", () => {
  const copied = new Set(cssNames);
  const missing = readdirSync(new URL("tokens/", REF))
    .filter((f) => f.endsWith(".css") && !copied.has(f))
    .sort();
  assert.deepEqual(missing, ["fonts.css"]);
});

test("ds/lucidase.preset.cjs equals the reference preset except the recorded differences", () => {
  const app = read(new URL("lucidase.preset.cjs", APP));
  const ref = read(new URL("tailwind/lucidase.preset.js", REF));
  // The leading doc comment is prose about where the file comes from; compare the code after it.
  const code = (s) => s.slice(s.indexOf("*/") + 2);
  // Each recorded replacement must apply on its own, so one that becomes a no-op fails the test.
  const swap = (s, from, to) => {
    assert.ok(s.includes(from), `the reference preset no longer contains the recorded original: ${from}`);
    return s.replace(from, to);
  };
  let expected = code(ref);
  // README: motion values aligned with motion.css (240 ms, ease-out-quart)
  expected = swap(expected, 'slow: "300ms"', 'slow: "240ms"');
  expected = swap(expected, 'standard: "cubic-bezier(.2,0,0,1)"', 'standard: "cubic-bezier(.25,1,.5,1)"');
  // formatting only: the app copy does not quote the `header` key
  expected = swap(expected, 'spacing: { "header": v("header-h") }', 'spacing: { header: v("header-h") }');
  assert.equal(code(app), expected);
});
