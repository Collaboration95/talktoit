import { chromium } from "playwright";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import {
  comparisonOracle,
  equal,
  near,
  questions,
  requireCriterion,
  withinViewport,
  zeroMissingOracle,
} from "./contracts.mjs";

const [phase, base, privateDir, artifacts, python] = process.argv.slice(2);
const execute = promisify(execFile);
const criteria = {};
let current = "browser-start";
let page;
let context;
let browser;
let exit = 1;
const errors = { page: 0, console: 0, external: 0, request: 0, http: 0 };

async function criterion(name, action) {
  current = name;
  console.log(JSON.stringify({ checking: name }));
  await action();
  criteria[name] = true;
}

async function json(path) {
  const response = await context.request.get(base + path);
  equal(response.status(), 200, "http-oracle-status");
  return response.json();
}

async function until(predicate, name, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await predicate();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(name);
}

async function visible(text) {
  await page.getByText(text, { exact: true }).first().waitFor();
}

async function shot(name) {
  await page.evaluate(() => document.fonts.ready);
  // Visual settling only; never used to establish data/job readiness or timings.
  await page.waitForTimeout(300);
  const dimensions = await page.evaluate(() => ({
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  // Layout failures are accumulated so cancellation/restart still run. They
  // remain failing criteria and make the final command fail; none is waived.
  try {
    withinViewport(dimensions, page.viewportSize().width);
    criteria[`layout-${name}`] = true;
  } catch {
    criteria[`layout-${name}`] = false;
    console.log(
      JSON.stringify({
        failed: `layout-${name}`,
        code: "document-horizontal-overflow",
      }),
    );
  }
  await page.screenshot({
    path: join(artifacts, `${name}.png`),
    fullPage: true,
  });
}

async function tab(name) {
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
}

async function settings() {
  await tab("Settings");
  await page
    .getByRole("heading", { name: "Settings & data controls", exact: true })
    .waitFor();
  await page.getByLabel("Apple Health export file", { exact: true }).waitFor();
  await until(
    async () =>
      !(await page
        .getByText("Checking active imports…", { exact: true })
        .isVisible()),
    "import-discovery",
  );
}

async function upload(filename) {
  const previous = new Set((await json("/api/imports")).map((job) => job.id));
  await page
    .getByLabel("Apple Health export file", { exact: true })
    .setInputFiles(join(privateDir, filename));
  const [response] = await Promise.all([
    page.waitForResponse(
      (r) =>
        new URL(r.url()).pathname === "/api/imports" &&
        r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Import export", exact: true }).click(),
  ]);
  equal(response.status(), 202, "native-upload-status");
  // Chromium may evict POST bodies from its inspector cache. The public job
  // list is durable and independent of DevTools' response body retention.
  const created = (await json("/api/imports")).filter(
    (job) => !previous.has(job.id),
  );
  equal(created.length, 1, "one-new-upload-job");
  equal(created[0].filename, filename, "native-upload-filename");
  return created[0];
}

async function finished(job, state) {
  return until(
    async () => {
      const result = await json(`/api/imports/${job.id}`);
      if (["failed", "succeeded"].includes(result.state)) {
        equal(result.state, state, "terminal-job-state");
        return result;
      }
      return false;
    },
    "import-terminal-timeout",
    60000,
  );
}

async function cli(question) {
  const { stdout } = await execute(
    python,
    [
      fileURLToPath(new URL("./cli.py", import.meta.url)),
      "--question",
      question,
      "--json",
      "--cache-mode",
      "fresh",
    ],
    {
      env: process.env,
      timeout: 30000,
      maxBuffer: 4 * 1024 * 1024,
    },
  );
  return JSON.parse(stdout);
}

async function denials() {
  try {
    return await readFile(join(privateDir, "denials"), "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return "";
    throw error;
  }
}

async function ask(question, template, heading) {
  const priorDenials = await denials();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  const input = page.getByPlaceholder("Ask about your health data…");
  await input.fill(question);
  // Keyboard submission exercises the actual form, not a direct API call.
  const [response] = await Promise.all([
    page.waitForResponse(
      (r) =>
        new URL(r.url()).pathname === "/api/chat" &&
        r.request().method() === "POST",
    ),
    input.press("Enter"),
  ]);
  equal(response.status(), 200, "browser-chat-status");
  const body = await response.json();
  equal(body.template_id, template, "browser-chat-template");
  await page
    .getByRole("paragraph")
    .filter({ hasText: question })
    .first()
    .waitFor();
  await page
    .getByRole("button", { name: "Hide answer details", exact: true })
    .waitFor();
  if (heading)
    await page.getByRole("heading", { name: heading, exact: true }).waitFor();
  else if (body.narrative) await visible(body.narrative);
  const independent = await cli(question);
  equal(body.data, independent.data, "cli-browser-http-data-parity");
  equal(
    body.metadata.dataset_version_id,
    independent.metadata.dataset_version_id,
    "cli-browser-http-identity",
  );
  const status = await json("/api/status");
  equal(
    body.metadata.dataset_version_id,
    status.dataset.id,
    "answer-current-dataset",
  );
  const bodyText = await page.locator("body").innerText();
  requireCriterion(bodyText.includes(question), "original-question-visible");
  requireCriterion(
    !/SELECT\s|Traceback|tool_name|"template_id"|"arguments"/.test(bodyText),
    "no-implementation-leak",
  );
  const newDenials = (await denials()).slice(priorDenials.length);
  if (question === "What should I eat?") {
    requireCriterion(
      /^(provider\n)+$/.test(newDenials),
      "open-planning-denied-before-provider-execution",
    );
  } else {
    equal(newDenials, "", "recognized-questions-never-attempt-inference");
  }
  return body;
}

async function active(job) {
  const latest = await until(async () => {
    const value = await json(`/api/imports/${job.id}`);
    requireCriterion(
      value.state !== "succeeded" && value.state !== "failed",
      "real-import-ended-before-action",
    );
    return value.state === "running" && value.started_at ? value : false;
  }, "real-import-running");
  equal(latest.progress, 0, "no-invented-import-progress");
  await page
    .getByRole("button", { name: "Cancel import", exact: true })
    .waitFor();
  await page
    .getByRole("status")
    .filter({ hasText: `${job.filename} · running` })
    .waitFor();
  return latest;
}

async function journey() {
  let identity;
  await criterion("empty-onboarding-keyboard-settings", async () => {
    await page.goto(base + "/?tab=chat");
    equal(
      (await json("/api/status")).readiness,
      "no_active_import",
      "empty-state-oracle",
    );
    const open = page.getByRole("button", {
      name: "Open Settings to import",
      exact: true,
    });
    await open.focus();
    await page.keyboard.press("Enter");
    await page
      .getByLabel("Apple Health export file", { exact: true })
      .waitFor();
    await visible("No health dataset has been imported yet.");
    await shot("onboarding-settings-desktop");
  });
  await criterion("native-xml-upload-known-values-identity", async () => {
    const job = await upload("sample.xml");
    const terminal = await finished(job, "succeeded");
    equal(terminal.progress, 100, "successful-job-progress");
    await page
      .getByRole("status")
      .filter({ hasText: "sample.xml · succeeded" })
      .waitFor();
    const status = await json("/api/status");
    equal(status.readiness, "ready", "import-ready");
    equal(
      [status.dataset.coverage_start, status.dataset.coverage_end],
      ["2026-06-01", "2026-06-10"],
      "sample-coverage",
    );
    equal(status.dataset.counts.workouts, 3, "sample-workout-count");
    identity = status.dataset.id;
    requireCriterion(/^ds_/.test(identity), "dataset-identity");
    const steps = await json(
      "/api/dashboard/steps?start=2026-06-01&end=2026-06-10&granularity=day",
    );
    near(
      steps.series.reduce((sum, point) => sum + (point.value ?? 0), 0),
      90954,
      "sample-step-total",
    );
    await tab("Chat");
    const workout = await ask(questions.workout, "workout_card", "Running");
    near(workout.data.duration_minutes, 45.5, "sample-run-duration");
    await visible("46 min");
    await shot("workout-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    await shot("workout-phone");
  });
  await criterion(
    "scoped-dashboard-filter-zero-reset-keyboard-route",
    async () => {
      await tab("Dashboard");
      await page
        .getByRole("button", { name: "Latest 7 data days", exact: true })
        .click();
      await until(
        async () =>
          (await page
            .getByLabel("Period start", { exact: true })
            .inputValue()) === "2026-06-04",
        "dataset-anchored-period",
      );
      equal(
        await page.getByLabel("Period end", { exact: true }).inputValue(),
        "2026-06-10",
        "dataset-anchored-end",
      );
      await page.getByLabel("Period start", { exact: true }).fill("2026-06-01");
      await page.getByLabel("Period end", { exact: true }).fill("2026-06-07");
      await page.getByLabel("Period end", { exact: true }).press("Enter");
      await page.getByRole("button", { name: /^Running \d$/ }).click();
      await page
        .getByLabel("Filter workouts by source", { exact: true })
        .selectOption("Strava");
      await visible("No workouts match this scope. Change filters or Reset.");
      const scoped = new URL(page.url()).searchParams;
      equal(
        [
          scoped.get("start"),
          scoped.get("end"),
          scoped.get("activity_type"),
          scoped.get("source"),
        ],
        ["2026-06-01", "2026-06-07", "Running", "Strava"],
        "filter-url-state",
      );
      const oracle = await json(
        "/api/dashboard/workouts?start=2026-06-01&end=2026-06-07&activity_type=Running&source=Strava",
      );
      equal(oracle.workouts.length, 0, "filter-http-zero");
      await shot("zero-results-phone");
      const reset = page.getByRole("button", { name: "Reset", exact: true });
      await reset.focus();
      await page.keyboard.press("Enter");
      const run = page.getByRole("button", { name: /5 Jun 2026.*Running/ });
      await run.waitFor();
      requireCriterion(
        !new URL(page.url()).searchParams.has("source"),
        "reset-clears-source",
      );
      await shot("dashboard-phone");
      await page.setViewportSize({ width: 1440, height: 900 });
      await shot("dashboard-desktop");
      await run.focus();
      await page.keyboard.press("Enter");
      // The XML's run references a GPX that was deliberately not uploaded.
      await visible("Route could not be read");
      await page.getByText(/companion route file is unreadable/).waitFor();
      await page
        .getByRole("button", { name: "← Back to list", exact: true })
        .click();
      const strength = page.getByRole("button", {
        name: /6 Jun 2026.*Traditional Strength Training/,
      });
      await strength.focus();
      await page.keyboard.press("Enter");
      await visible("No route available");
      await page
        .getByText(/XML uploads do not include companion GPX files/)
        .waitFor();
      await shot("route-absence-desktop");
      await page.setViewportSize({ width: 390, height: 844 });
      await shot("route-absence-phone");
      await page
        .getByRole("button", { name: "← Back to list", exact: true })
        .click();
    },
  );
  await criterion("sleep-union-stages-http-cli-browser-parity", async () => {
    await tab("Chat");
    const sleep = await ask(questions.sleep, "trend_chart");
    const dashboard = await json(
      "/api/dashboard/sleep?start=2026-06-01&end=2026-06-10&granularity=day",
    );
    equal(sleep.data.series, dashboard.series, "sleep-dashboard-series-parity");
    const values = Object.fromEntries(
      sleep.data.series.map((point) => [point.bucket, point.value]),
    );
    near(values["2026-06-05"], 7.5, "sleep-overlap-union");
    near(values["2026-06-08"], 7, "sleep-known-day");
    near(
      sleep.data.series.reduce((sum, point) => sum + (point.value ?? 0), 0),
      14.5,
      "sleep-union-total",
    );
    equal(values["2026-06-06"], null, "sleep-missing-bucket");
    requireCriterion(
      sleep.narrative.includes("awake and in-bed"),
      "sleep-measurement-disclosure",
    );
    await until(
      async () => (await page.locator("canvas").count()) > 0,
      "sleep-chart-rendered",
    );
    await shot("sleep-phone");
    const stages = await json(
      "/api/dashboard/sleep/stages?start=2026-06-01&end=2026-06-10",
    );
    equal(stages.stage_data_available, true, "sleep-stages-available");
    near(stages.total_asleep_hours, 14.5, "sleep-stage-union");
    requireCriterion(
      Object.values(stages.stages_hours).reduce((a, b) => a + b, 0) <=
        stages.total_asleep_hours,
      "sleep-stage-partition",
    );
    await tab("Dashboard");
    await page
      .getByRole("button", { name: "All available data", exact: true })
      .click();
    await visible("Measured asleep time: 14.5 h");
    await page
      .getByLabel("Measured sleep stage durations", { exact: true })
      .waitFor();
    await shot("sleep-stages-phone");
    await tab("Chat");
    const unsupported = await ask(
      "Why did I sleep badly?",
      "fallback",
      "Not supported yet",
    );
    equal(
      unsupported.data.reason,
      "unsupported",
      "sleep-interpretation-unsupported",
    );
  });
  await criterion("unequal-coverage-comparison-http-cli-browser", async () => {
    const comparison = await ask(
      questions.comparison,
      "comparison",
      "Measured metric comparison",
    );
    comparisonOracle(comparison);
    await visible("Steps per observed day");
    for (const coverage of [
      "3/3 days",
      "7/7 days",
      "2/3 days",
      "3/7 days",
      "1/3 days",
      "2/7 days",
    ])
      await visible(coverage);
    await shot("comparison-phone");
    await page.setViewportSize({ width: 1440, height: 900 });
    await shot("comparison-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    const missing = await ask(
      questions.missing,
      "comparison",
      "Measured metric comparison",
    );
    requireCriterion(
      missing.data.metrics.every(
        (row) => row.last_value === null && row.delta === null,
      ),
      "comparison-missing-period",
    );
    await visible("0/7 days");
    await shot("missing-comparison-phone");
    const workouts = await ask(
      "Compare my running this month vs last month",
      "comparison",
    );
    const sessions = workouts.data.metrics.find(
      (row) => row.label === "Sessions",
    );
    requireCriterion(sessions, "legacy-workout-comparison-present");
    equal(
      [sessions.this_value, sessions.last_value],
      [1, 0],
      "legacy-workout-comparison-values",
    );
  });
  await criterion(
    "actionable-fallback-original-question-keyboard",
    async () => {
      const empty = await ask(
        "Show daily sleep from 2025-01-01 to 2025-01-07",
        "fallback",
        "No matching measurements",
      );
      equal(empty.data.reason, "no_matching_data", "empty-reason");
      const clarify = await ask(
        "Compare steps this week",
        "fallback",
        "A little more detail needed",
      );
      equal(
        clarify.data.reason,
        "clarification_needed",
        "clarification-reason",
      );
      requireCriterion(
        clarify.data.text.includes("two complete date ranges"),
        "actionable-clarification",
      );
      await visible(clarify.data.text);
      await shot("fallback-phone");
      const details = page.getByRole("button", {
        name: "Hide answer details",
        exact: true,
      });
      await details.focus();
      await page.keyboard.press("Enter");
      await page
        .getByRole("button", { name: "Show answer details", exact: true })
        .press("Enter");
      await page
        .getByRole("heading", {
          name: "A little more detail needed",
          exact: true,
        })
        .waitFor();
      const unavailable = await ask(
        "What should I eat?",
        "fallback",
        "Question provider unavailable",
      );
      equal(
        unavailable.data.reason,
        "provider_unavailable",
        "provider-fallback-reason",
      );
    },
  );
  await criterion("real-job-navigation-reload-reconnect-cancel", async () => {
    await settings();
    await page.getByText(/This screen accepts XML only/).waitFor();
    const job = await upload("lifecycle.xml");
    await active(job);
    await tab("Chat");
    await settings();
    await active(job);
    await page.reload();
    await active(job);
    await shot("active-import-phone");
    await page
      .getByRole("button", { name: "Cancel import", exact: true })
      .click();
    const terminal = await finished(job, "failed");
    equal(
      terminal.error,
      "The import was cancelled.",
      "cancelled-backend-truth",
    );
    await page
      .getByRole("status")
      .filter({ hasText: "lifecycle.xml · Cancelled" })
      .waitFor();
    equal(
      (await json("/api/status")).dataset.id,
      identity,
      "cancel-preserves-dataset",
    );
    await shot("cancelled-import-phone");
  });
  await criterion("real-job-running-before-hard-stop", async () => {
    const job = await upload("lifecycle.xml");
    await active(job);
    // Private handoff only; no opaque IDs are published in the receipt.
    await writeFile(
      join(privateDir, "handoff.json"),
      JSON.stringify({ job: job.id, identity }),
    );
  });
}

async function recovery() {
  await criterion("hard-stop-restart-durable-job-ui-truth", async () => {
    const handoff = JSON.parse(
      await readFile(join(privateDir, "handoff.json"), "utf8"),
    );
    const terminal = await json(`/api/imports/${handoff.job}`);
    equal(terminal.state, "failed", "restart-job-failed");
    equal(
      terminal.error,
      "The import was interrupted. Choose your export to try again.",
      "restart-job-actionable",
    );
    equal(terminal.progress, 0, "restart-no-success-progress");
    equal(
      (await json("/api/status")).dataset.id,
      handoff.identity,
      "restart-preserves-identity",
    );
    await page.goto(base + "/?tab=settings");
    await visible(terminal.error);
    await page
      .getByRole("status")
      .filter({ hasText: "lifecycle.xml · failed" })
      .waitFor();
    equal(
      await page
        .getByRole("button", { name: "Cancel import", exact: true })
        .count(),
      0,
      "restart-no-active-cancel",
    );
    await shot("recovered-job-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    await shot("recovered-job-phone");
    await tab("Chat");
    const workout = await ask(questions.workout, "workout_card", "Running");
    near(workout.data.duration_minutes, 45.5, "restart-known-value");
  });
  await criterion(
    "zero-versus-missing-browser-http-cli-new-identity",
    async () => {
      await settings();
      const before = (await json("/api/status")).dataset.id;
      const job = await upload("zero.xml");
      await finished(job, "succeeded");
      await page
        .getByRole("status")
        .filter({ hasText: "zero.xml · succeeded" })
        .waitFor();
      requireCriterion(
        (await json("/api/status")).dataset.id !== before,
        "replacement-mints-new-identity",
      );
      await tab("Chat");
      const zero = await ask(
        questions.zero,
        "comparison",
        "Measured metric comparison",
      );
      zeroMissingOracle(zero);
      const row = page
        .getByRole("row")
        .filter({ hasText: "Steps per observed day" });
      requireCriterion(
        (await row.innerText()).includes("0 steps/day"),
        "zero-rendered-numerically",
      );
      requireCriterion(
        (await row.innerText()).includes("—"),
        "missing-rendered-dash",
      );
      await visible("1/1 days");
      await visible("0/1 days");
      await shot("zero-missing-phone");
      await page.setViewportSize({ width: 1440, height: 900 });
      await shot("zero-missing-desktop");
    },
  );
}

try {
  browser = await chromium.launch();
  await writeFile(
    join(privateDir, "browser-runtime.json"),
    JSON.stringify({
      playwright: JSON.parse(
        await readFile(
          new URL("./node_modules/playwright/package.json", import.meta.url),
          "utf8",
        ),
      ).version,
      chromium: browser.version(),
    }),
  );
  context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    serviceWorkers: "block",
  });
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin === base) return route.continue();
    errors.external++;
    return route.abort("blockedbyclient");
  });
  await context.routeWebSocket("**/*", (socket) => {
    errors.external++;
    socket.close();
  });
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", () => errors.page++);
  page.on("console", (message) => {
    if (message.type() === "error") errors.console++;
  });
  page.on("requestfailed", (request) => {
    // Unmounted panels deliberately abort in-flight fetches; every other failure
    // remains a failing criterion (no retries, broad suppression or body logging).
    if (request.failure()?.errorText !== "net::ERR_ABORTED") errors.request++;
  });
  page.on("response", (response) => {
    if (response.status() >= 400) errors.http++;
  });
  await (phase === "journey" ? journey() : recovery());
  await criterion(`${phase}-no-browser-errors-or-external-egress`, async () => {
    for (const [category, count] of Object.entries(errors))
      criteria[`${phase}-no-${category}-errors`] = count === 0;
    requireCriterion(
      Object.values(errors).every((count) => count === 0),
      "unexpected-browser-network-or-runtime-error",
    );
  });
  exit = Object.values(criteria).every((value) => value === true) ? 0 : 1;
} catch (error) {
  criteria[current] = false;
  const code = /^[a-z][a-z0-9-]{0,100}$/.test(error.message)
    ? error.message
    : error.name;
  console.log(
    JSON.stringify({
      failed: current,
      code,
      location: error.stack?.match(/browser\.mjs:\d+:\d+/)?.[0],
      systemCode: error.code,
    }),
  );
  if (page) {
    await page
      .screenshot({
        path: join(artifacts, `${phase}-failure.png`),
        fullPage: true,
      })
      .catch(() => {});
  }
} finally {
  if (browser) await browser.close();
  await writeFile(join(privateDir, `${phase}.json`), JSON.stringify(criteria));
  process.exitCode = exit;
}
