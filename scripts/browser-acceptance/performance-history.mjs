import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { summarize } from "./performance-report.mjs";
const base = new URL(
  "../../docs/decisions/evidence/main-a0ac-performance-revise/",
  import.meta.url,
);
const expected = {
  "main-performance.md":
    "235018f9af1f8e27818233445e892345862110339d5ac203224fa7d137d8ef24",
  "main-performance-results.json":
    "f89c33d170d3efc994fe5821fd31b863481ebed8e5454505210383cd4a30aac1",
};
for (const [name, sha] of Object.entries(expected))
  assert.equal(
    createHash("sha256")
      .update(await readFile(new URL(name, base)))
      .digest("hex"),
    sha,
    "immutable-historical-evidence",
  );
const r = JSON.parse(
  await readFile(new URL("main-performance-results.json", base), "utf8"),
);
assert.equal(r.main_head, "a0ac51b6a24442f669608f153efe5b0c98931051");
assert.equal(r.verdict.status, "REVISE");
assert.equal(r.reference_head, "859f89a405499ecef024fb8dde127a5f3d7c2f77");
let strings = 0;
function privacy(value) {
  if (Array.isArray(value)) return value.forEach(privacy);
  if (value && typeof value === "object")
    return Object.values(value).forEach(privacy);
  if (typeof value === "string") {
    strings++;
    assert.ok(
      !value.includes("/Users/") &&
        !value.includes("/tmp/") &&
        !value.includes("://") &&
        !value.includes("SELECT "),
      "historical-public-privacy",
    );
  }
}
privacy(r);
for (const group of [r.browser_primary, r.browser_confirmation])
  for (const browser of Object.values(group)) {
    const retained = browser.raw_trials.filter((row) => row.retained);
    assert.equal(retained.length, 20);
    assert.equal(browser.raw_trials.length, 22);
    for (const [name, s] of Object.entries(browser.measurements)) {
      const actual = summarize(retained.map((row) => row[name]));
      for (const key of Object.keys(actual))
        assert.ok(
          Math.abs(actual[key] - s[key]) < 1e-7,
          "historical-statistic-recomputation",
        );
    }
    assert.equal(
      browser.failed_requests,
      retained.reduce((n, row) => n + row.failed_requests, 0),
    );
  }
assert.equal(r.thresholds.median_regression_percent, 10);
assert.equal(r.thresholds.p95_regression_percent, 15);
assert.equal(r.thresholds.absolute_floor_ms, 5);
console.log(
  JSON.stringify({
    immutableHistoricalRevise: true,
    closedPackageHash: true,
    publicStringsChecked: strings,
    browserRecomputation: true,
  }),
);
