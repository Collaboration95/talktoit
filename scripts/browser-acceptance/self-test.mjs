import assert from "node:assert/strict";
import { chromium } from "playwright";
import {
  equal,
  requireCriterion,
  withinViewport,
  zeroMissingOracle,
} from "./contracts.mjs";

// Mutation sensitivity: a plausible-looking zero substitution must fail the same
// acceptance assertion used for real HTTP/CLI/browser results.
const envelope = {
  template_id: "comparison",
  data: {
    metrics: [
      {
        unit: "steps/day",
        this_value: 0,
        last_value: null,
        this_observed_days: 1,
        last_observed_days: 0,
      },
      { unit: "bpm", this_value: null, last_value: 42 },
      { unit: "ms", this_value: 30, last_value: null },
    ].map((row) => ({
      ...row,
      delta: null,
      this_requested_days: 1,
      last_requested_days: 1,
    })),
  },
};
zeroMissingOracle(envelope);
const broken = structuredClone(envelope);
broken.data.metrics[0].this_value = null;
assert.throws(() => zeroMissingOracle(broken), /zero-is-not-missing/);
assert.throws(
  () => equal("wrong-dataset", "expected-dataset", "identity"),
  /identity/,
);

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.setContent(
    "<!doctype html><html><body><button>Recovery</button></body></html>",
  );
  const dimensions = () =>
    page.evaluate(() => ({
      width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
  withinViewport(await dimensions(), 390);
  await page.evaluate(() => {
    const broken = document.createElement("div");
    broken.style.width = "2000px";
    broken.style.height = "10px";
    document.body.append(broken);
  });
  let rejected = false;
  try {
    withinViewport(await dimensions(), 390);
  } catch {
    rejected = true;
  }
  requireCriterion(rejected, "injected-browser-overflow-not-detected");
  console.log(
    JSON.stringify({
      zeroMutationRejected: true,
      identityMutationRejected: true,
      browserOverflowMutationRejected: true,
    }),
  );
} finally {
  await browser.close();
}
