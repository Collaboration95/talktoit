import assert from "node:assert/strict";
import { test } from "node:test";
import {
  summarize,
  validateReport,
  browserReport,
  METRICS,
} from "./performance-report.mjs";

test("stats retain outliers and use nearest-rank p95, median and population sigma", () => {
  const s = summarize([1, 2, 3, 4, 100]);
  assert.equal(s.median, 3);
  assert.equal(s.p95, 100);
  assert.equal(s.samples, 5);
  assert.equal(s.maximum, 100);
  assert.ok(Math.abs(s.stddev - Math.sqrt(1522)) < 1e-10);
});
test("report excludes exactly two warmups and keeps all twenty retained trials per metric", () => {
  const rows = Array.from({ length: 22 }, (_, i) => ({
    ordinal: i + 1,
    retained: i >= 2,
    phase_requests: {
      mount: 9,
      toggle: 1,
      scope: 8,
      cached_chat: 0,
      cached_dashboard: 9,
    },
    metrics: Object.fromEntries(METRICS.map((m) => [m, i < 2 ? 10000 : i - 1])),
    errors: {
      requests: 27,
      transport_failures: 0,
      panel_transport_failures: 0,
      http_failures: 0,
      body_failures: 0,
      parse_failures: 0,
      aborts: 0,
      network_failures: 0,
      timeouts: 0,
      intentional_cancellations: 0,
      incomplete_bodies: 0,
      endpoints: Object.fromEntries(
        [
          "status",
          "summary",
          "workouts",
          "volume",
          "steps",
          "heart",
          "sleep",
          "sleep_stages",
          "capabilities",
          "other",
        ].map((e) => [
          e,
          e === "other" ? 0 : e === "status" ? 2 : e === "volume" ? 4 : 3,
        ]),
      ),
    },
  }));
  const report = browserReport(
    {
      mode: "qualification",
      role: "main",
      production_head: "a".repeat(40),
      harness_sha256: "b".repeat(64),
    },
    rows,
  );
  validateReport(report);
  assert.equal(report.samples, 20);
  assert.equal(report.warmups, 2);
  for (const metric of METRICS) {
    assert.equal(report.measurements[metric].median, 10.5);
    assert.equal(report.measurements[metric].p95, 19);
  }
  assert.throws(
    () => validateReport({ ...report, question: "private" }),
    /report/,
  );
  assert.throws(
    () => validateReport({ ...report, trials: rows.slice(1) }),
    /report/,
  );
  for (const name of [
    "transport_failures",
    "http_failures",
    "body_failures",
    "parse_failures",
    "intentional_cancellations",
    "incomplete_bodies",
  ]) {
    const tainted = structuredClone(report);
    tainted.trials[0].errors[name] = 1;
    assert.throws(() => validateReport(tainted), /report-normal-zero-errors/);
  }
  const bad = structuredClone(report);
  bad.trials[2].metrics.sql = 0;
  assert.throws(() => validateReport(bad), /report/);
});
