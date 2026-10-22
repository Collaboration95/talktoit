// Failures expose a criterion name, never response bodies, questions or records.
export function requireCriterion(value, criterion) {
  if (!value) throw new Error(criterion);
}

export function equal(actual, expected, criterion) {
  requireCriterion(
    JSON.stringify(actual) === JSON.stringify(expected),
    criterion,
  );
}

export function near(actual, expected, criterion) {
  requireCriterion(
    typeof actual === "number" && Math.abs(actual - expected) < 1e-7,
    criterion,
  );
}

export function comparisonOracle(envelope) {
  equal(envelope.template_id, "comparison", "comparison-template");
  const expectations = {
    "steps/day": [30800 / 3, 60154 / 7, 3, 7],
    bpm: [48.5, 51, 2, 3],
    ms: [38.9, 48.65, 1, 2],
  };
  equal(envelope.data.metrics.length, 3, "comparison-metric-count");
  for (const [
    unit,
    [current, previous, observed, priorObserved],
  ] of Object.entries(expectations)) {
    const row = envelope.data.metrics.find((metric) => metric.unit === unit);
    requireCriterion(row, "comparison-unit");
    near(row.this_value, current, "comparison-current-value");
    near(row.last_value, previous, "comparison-previous-value");
    near(row.delta, current - previous, "comparison-delta");
    equal(
      [row.this_observed_days, row.last_observed_days],
      [observed, priorObserved],
      "comparison-observed-days",
    );
    equal(
      [row.this_requested_days, row.last_requested_days],
      [3, 7],
      "comparison-unequal-periods",
    );
    equal(row.direction_tone, "neutral", "comparison-measured-only");
  }
}

export function zeroMissingOracle(envelope) {
  equal(envelope.template_id, "comparison", "zero-template");
  const rows = Object.fromEntries(
    envelope.data.metrics.map((row) => [row.unit, row]),
  );
  equal(
    [rows["steps/day"].this_value, rows["steps/day"].last_value],
    [0, null],
    "zero-is-not-missing",
  );
  equal(
    [
      rows["steps/day"].this_observed_days,
      rows["steps/day"].last_observed_days,
    ],
    [1, 0],
    "zero-observed-coverage",
  );
  equal(
    [rows.bpm.this_value, rows.ms.last_value],
    [null, null],
    "missing-is-not-zero",
  );
  requireCriterion(
    rows.bpm.last_value > 0 && rows.ms.this_value > 0,
    "present-metric-values",
  );
  for (const row of Object.values(rows)) {
    equal(row.delta, null, "missing-delta");
    equal(
      [row.this_requested_days, row.last_requested_days],
      [1, 1],
      "zero-requested-days",
    );
  }
}

export function withinViewport({ width, scrollWidth }, expected) {
  equal(width, expected, "viewport-width");
  requireCriterion(scrollWidth <= width, "document-horizontal-overflow");
}

export const questions = {
  workout: "Show my last run",
  sleep: "Show daily sleep from 2026-06-01 to 2026-06-10",
  stages: "Show my sleep stages from 2026-06-01 to 2026-06-10",
  comparison:
    "Compare steps, resting heart rate, and HRV from 2026-06-08 to 2026-06-10 vs 2026-06-01 to 2026-06-07",
  missing:
    "Compare steps, resting HR, and HRV between June 1–7 and May 25–31, 2026",
  zero: "Compare steps, resting heart rate, and HRV from 2024-01-01 to 2024-01-01 vs 2024-01-02 to 2024-01-02",
};
