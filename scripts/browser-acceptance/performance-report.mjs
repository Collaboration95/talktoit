import assert from "node:assert/strict";
import { validateNumeric } from "./performance-phase.mjs";
export const METRICS = Object.freeze([
  "cold_chat_ready_ms",
  "first_chart_canvas_ms",
  "cached_chat_shell_ms",
  "cached_dashboard_ms",
  "volume_response_plus_two_frames_ms",
  "first_chart_locator_upper_bound_ms",
]);
const keys = (value, expected) =>
  assert.deepEqual(
    Object.keys(value).sort(),
    [...expected].sort(),
    "report-closed-keys",
  );
export function summarize(values) {
  assert.ok(
    values.length > 0 && values.every((v) => Number.isFinite(v) && v >= 0),
    "report-observations",
  );
  const sorted = [...values].sort((a, b) => a - b),
    n = sorted.length,
    mean = values.reduce((a, b) => a + b, 0) / n;
  return {
    samples: n,
    median:
      n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2,
    p95: sorted[Math.ceil(0.95 * n) - 1],
    minimum: sorted[0],
    maximum: sorted[n - 1],
    stddev: Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / n),
  };
}
export function browserReport(identity, trials) {
  const retained = trials.filter((r) => r.retained);
  const report = {
    schema_version: 1,
    ...identity,
    samples: retained.length,
    warmups: trials.length - retained.length,
    trials,
    measurements:
      identity.mode === "qualification"
        ? Object.fromEntries(
            METRICS.map((m) => [
              m,
              summarize(retained.map((r) => r.metrics[m])),
            ]),
          )
        : {},
  };
  validateReport(report);
  return report;
}
export function validateReport(report) {
  keys(report, [
    "schema_version",
    "mode",
    "role",
    "production_head",
    "harness_sha256",
    "samples",
    "warmups",
    "trials",
    "measurements",
  ]);
  assert.equal(report.schema_version, 1, "report-version");
  assert.ok(
    ["functional", "qualification"].includes(report.mode),
    "report-mode",
  );
  assert.ok(["main", "reference"].includes(report.role), "report-role");
  assert.match(report.production_head, /^[a-f0-9]{40}$/, "report-head");
  assert.match(report.harness_sha256, /^[a-f0-9]{64}$/, "report-harness");
  const formal = report.mode === "qualification";
  assert.equal(report.samples, formal ? 20 : 1, "report-samples");
  assert.equal(report.warmups, formal ? 2 : 0, "report-warmups");
  assert.equal(
    report.trials.length,
    report.samples + report.warmups,
    "report-trial-count",
  );
  for (const [index, row] of report.trials.entries()) {
    keys(row, ["ordinal", "retained", "metrics", "errors", "phase_requests"]);
    assert.equal(row.ordinal, index + 1, "report-ordinal");
    assert.equal(
      row.retained,
      index >= report.warmups,
      "report-warmup-membership",
    );
    keys(row.metrics, formal ? METRICS : []);
    for (const n of Object.values(row.metrics))
      assert.ok(Number.isFinite(n) && n >= 0, "report-metric");
    validateNumeric(row.errors);
    assert.ok(
      Object.entries(row.errors)
        .filter(([name]) => !["requests", "endpoints"].includes(name))
        .every(([, value]) => value === 0),
      "report-normal-zero-errors",
    );
    assert.deepEqual(
      row.phase_requests,
      {
        mount: 9,
        toggle: report.role === "reference" ? 8 : 1,
        scope: 8,
        cached_chat: 0,
        cached_dashboard: 9,
      },
      "report-exact-phase-requests",
    );
    assert.equal(
      Object.values(row.phase_requests).reduce((a, b) => a + b, 0),
      Object.entries(row.errors.endpoints)
        .filter(([key]) => key !== "other")
        .reduce((n, [, value]) => n + value, 0),
      "report-request-ledger-reconciliation",
    );
  }
  keys(report.measurements, formal ? METRICS : []);
  if (formal)
    for (const name of METRICS)
      assert.deepEqual(
        report.measurements[name],
        summarize(
          report.trials.filter((r) => r.retained).map((r) => r.metrics[name]),
        ),
        "report-recomputed-statistic",
      );
  return report;
}

export function failureReport(identity, stage, completed, errors) {
  const stages = [
    "start",
    "cold_chat",
    "first_chart",
    "mount",
    "toggle",
    "scope",
    "cached_chat",
    "cached_dashboard",
  ];
  assert.ok(stages.includes(stage), "report-failure-stage");
  validateNumeric(errors);
  const report = {
    schema_version: 1,
    ...identity,
    status: "incomplete",
    failed_stage: stage,
    completed_trials: completed.length,
    completed_retained: completed.filter((r) => r.retained).length,
    attempted_trial: completed.length + 1,
    errors,
  };
  keys(report, [
    "schema_version",
    "mode",
    "role",
    "production_head",
    "harness_sha256",
    "status",
    "failed_stage",
    "completed_trials",
    "completed_retained",
    "attempted_trial",
    "errors",
  ]);
  assert.ok(
    Number.isInteger(report.completed_trials) && report.completed_trials >= 0,
    "report-completed-trials",
  );
  return report;
}
