import assert from "node:assert/strict";
import { parseArgs } from "node:util";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";
import {
  canonicalBase,
  RequestLedger,
  panelExpectations,
  settlePhase,
} from "./performance-phase.mjs";
import {
  capturePreviousCanvases,
  waitForRenderedPanels,
} from "./performance-render.mjs";
import { browserReport, failureReport } from "./performance-report.mjs";

const { values: args } = parseArgs({
  options: {
    base: { type: "string" },
    generation: { type: "string" },
    private: { type: "string" },
    mode: { type: "string", default: "functional" },
    role: { type: "string", default: "main" },
    head: { type: "string" },
    harness: { type: "string" },
    "toggle-count": { type: "string", default: "1" },
    channel: { type: "string" },
    review: { type: "string" },
  },
});
assert.ok(["functional", "qualification"].includes(args.mode), "mode");
const qualifying = args.mode === "qualification";
if (qualifying) {
  const review = JSON.parse(await readFile(args.review, "utf8"));
  assert.equal(review.status, "PASS", "independent-method-review-required");
  assert.equal(review.protocol, "body-render-v1", "reviewed-protocol-required");
}
const base = canonicalBase(args.base);
assert.ok(
  ["127.0.0.1", "localhost"].includes(new URL(base).hostname),
  "loopback-required",
);
const toggleCount = Number(args["toggle-count"]);
assert.ok([1, 8].includes(toggleCount), "declared-toggle-count");
const browser = await chromium.launch(
  args.channel ? { channel: args.channel } : {},
);
const trials = [];
let blocked = 0;
let stage = "start";
let ledger;
let page;
let context;
const frames = (page) =>
  page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() =>
          requestAnimationFrame(() => resolve(performance.now())),
        ),
      ),
  );
const input = (page) =>
  page.locator('textarea[placeholder="Ask about your health data…"]:enabled');
try {
  for (let trial = 0; trial < (qualifying ? 22 : 1); trial++) {
    context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      serviceWorkers: "block",
    });
    await context.route("**/*", (route) => {
      if (
        ["127.0.0.1", "localhost"].includes(
          new URL(route.request().url()).hostname,
        )
      )
        return route.continue();
      blocked++;
      return route.abort();
    });
    assert.equal(
      (await context.request.post(base + "/__performance/reset")).status(),
      200,
      "reset-status",
    );
    page = await context.newPage();
    ledger = new RequestLedger(page);
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.name));
    // Diagnostic observations only; the primary clock still starts before the
    // locator click and ends after the visible/enabled locator and two frames.
    await page.addInitScript(() => {
      window.__ttiChatDiagnostic = {};
      let active = false;
      document.addEventListener(
        "click",
        (event) => {
          if (event.target.closest?.("nav button")?.textContent === "Chat") {
            active = true;
            window.__ttiChatDiagnostic = { dispatch_ms: performance.now() };
          }
        },
        true,
      );
      new MutationObserver(() => {
        if (active) {
          const field = document.querySelector(
            'textarea[placeholder="Ask about your health data…"]',
          );
          if (
            field &&
            !field.disabled &&
            field.getBoundingClientRect().height > 0
          ) {
            window.__ttiChatDiagnostic.input_visible_ms = performance.now();
            active = false;
          }
        }
      }).observe(document, { childList: true, subtree: true });
    });
    stage = "cold_chat";
    await page.goto(base + "/?tab=chat", { waitUntil: "domcontentloaded" });
    await input(page).waitFor({ state: "visible" });
    const cold = await frames(page);
    assert.equal(await page.evaluate(() => innerWidth), 390);
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= 390),
      "horizontal-overflow",
    );
    const question = "Show daily steps from 2024-01-01 to 2024-06-28";
    await input(page).fill(question);
    stage = "first_chart";
    const start = await page.evaluate(() => {
      window.__benchCanvas = {};
      const visit = () => {
        const canvas = document.querySelector("canvas");
        if (
          canvas &&
          canvas.width > 0 &&
          canvas.height > 0 &&
          canvas.getBoundingClientRect().width > 0 &&
          canvas.getBoundingClientRect().height > 0 &&
          getComputedStyle(canvas).visibility !== "hidden"
        ) {
          requestAnimationFrame(() =>
            requestAnimationFrame(
              () => (window.__benchCanvas.ready = performance.now()),
            ),
          );
        } else requestAnimationFrame(visit);
      };
      requestAnimationFrame(visit);
      return performance.now();
    });
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          new URL(r.url()).pathname === "/api/chat" &&
          r.request().method() === "POST",
      ),
      page.getByRole("button", { name: "Ask", exact: true }).click(),
    ]);
    assert.equal(response.status(), 200);
    const answer = await response.json();
    assert.equal(answer.template_id, "trend_chart");
    assert.equal(answer.metadata.provenance, "deterministic_local");
    assert.equal(
      answer.metadata.dataset_version_id,
      args.generation,
      "chat-generation",
    );
    await page.locator("canvas").first().waitFor({ state: "visible" });
    const chartUpper = (await frames(page)) - start;
    const chart =
      (await page.evaluate(async () => {
        while (window.__benchCanvas.ready === undefined)
          await new Promise((resolve) => requestAnimationFrame(resolve));
        return window.__benchCanvas.ready;
      })) - start;
    assert.ok((await page.locator("body").innerText()).includes(question));
    await ledger.drain();
    ledger.assertNormal();

    stage = "mount";
    await capturePreviousCanvases(page);
    const mount = ledger.begin("mount", panelExpectations("mount"));
    await page.getByRole("button", { name: "Dashboard", exact: true }).click();
    await settlePhase(page, mount, () => waitForRenderedPanels(page, mount));
    const status = (await mount.bodies()).status;
    assert.equal(status.dataset.id, args.generation, "mount-generation");
    stage = "toggle";
    await capturePreviousCanvases(page);
    const toggle = ledger.begin(
      "toggle",
      panelExpectations("toggle", {}, "month", toggleCount),
    );
    const volumeStart = await page.evaluate(() => performance.now());
    const [volumeResponse] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/dashboard/volume") &&
          r.url().includes("granularity=month"),
      ),
      page.getByRole("button", { name: /^month$/i }).click(),
    ]);
    assert.equal(await volumeResponse.finished(), null);
    const volumeReady = (await frames(page)) - volumeStart;
    await settlePhase(page, toggle, () =>
      waitForRenderedPanels(page, toggle, { granularity: "month" }),
    );
    stage = "scope";
    await capturePreviousCanvases(page);
    // Dates come from the generated dataset, never the system clock or a sleep.
    const end = status.dataset.coverage_end;
    const first = new Date(end + "T00:00:00Z");
    first.setUTCDate(first.getUTCDate() - 6);
    const scope = { start: first.toISOString().slice(0, 10), end };
    const scoped = ledger.begin(
      "scope",
      panelExpectations("scope", scope, "month"),
    );
    await page
      .getByRole("button", { name: "Latest 7 data days", exact: true })
      .click();
    await settlePhase(page, scoped, () =>
      waitForRenderedPanels(page, scoped, { scope, granularity: "month" }),
    );
    await ledger.drain();
    ledger.assertNormal();

    stage = "cached_chat";
    ledger.begin("cached_chat", []);
    const chatStart = await page.evaluate(() => performance.now());
    await page.getByRole("button", { name: "Chat", exact: true }).click();
    const actionReturnEpoch = Date.now();
    await input(page).waitFor({ state: "visible" });
    const cachedChat = (await frames(page)) - chatStart;
    const diagnostic = await page.evaluate(() => window.__ttiChatDiagnostic);
    await ledger.drain();
    ledger.assertNormal();
    stage = "cached_dashboard";
    await capturePreviousCanvases(page);
    const remount = ledger.begin(
      "cached_dashboard",
      panelExpectations("cached_dashboard", scope),
    );
    const dashStart = await page.evaluate(() => performance.now());
    await page.getByRole("button", { name: "Dashboard", exact: true }).click();
    await page.getByRole("button", { name: /^month$/i }).waitFor();
    await page.locator("canvas").first().waitFor({ state: "visible" });
    const cachedDashboard = (await frames(page)) - dashStart;
    await settlePhase(page, remount, () =>
      waitForRenderedPanels(page, remount, { scope }),
    );
    assert.equal(
      (await remount.bodies()).status.dataset.id,
      args.generation,
      "remount-generation",
    );
    await ledger.drain();
    ledger.assertNormal();
    assert.deepEqual(pageErrors, []);
    assert.equal(blocked, 0, "external-request");
    const counters = await (
      await context.request.get(base + "/__performance/counters")
    ).json();
    assert.equal(counters.provider_calls, 0);
    assert.equal(counters.network_attempts, 0);
    const metrics = qualifying
      ? {
          cold_chat_ready_ms: cold,
          first_chart_canvas_ms: chart,
          first_chart_locator_upper_bound_ms: chartUpper,
          cached_chat_shell_ms: cachedChat,
          cached_dashboard_ms: cachedDashboard,
          volume_response_plus_two_frames_ms: volumeReady,
        }
      : {};
    trials.push({
      ordinal: trial + 1,
      retained: !qualifying || trial >= 2,
      metrics,
      phase_requests: {
        mount: ledger.phaseRows(mount).length,
        toggle: ledger.phaseRows(toggle).length,
        scope: ledger.phaseRows(scoped).length,
        cached_chat: 0,
        cached_dashboard: ledger.phaseRows(remount).length,
      },
      errors: ledger.numeric(),
    });
    await writeFile(
      join(args.private, `trial-${trial + 1}-private.json`),
      JSON.stringify(
        {
          stage,
          rows: ledger.rows,
          events: ledger.events,
          diagnostic,
          action_return_epoch_ms: actionReturnEpoch,
          provider_counters: counters,
          phase_counts: {
            mount: ledger.phaseRows(mount).length,
            toggle: ledger.phaseRows(toggle).length,
            scope: ledger.phaseRows(scoped).length,
            cached_dashboard: ledger.phaseRows(remount).length,
          },
        },
        null,
        2,
      ),
    );
    await writeFile(
      join(args.private, "raw-numeric-trials.json"),
      JSON.stringify(trials, null, 2),
    );
    ledger.close();
    ledger = null;
    await context.close();
    context = null;
  }
  const report = browserReport(
    {
      mode: args.mode,
      role: args.role,
      production_head: args.head,
      harness_sha256: args.harness,
    },
    trials,
  );
  await writeFile(
    join(args.private, "public-summary.json"),
    JSON.stringify(report, null, 2),
  );
  console.log(
    JSON.stringify({
      functional: !qualifying,
      retained: report.samples,
      warmups: report.warmups,
      normal_zero_errors: true,
    }),
  );
} catch (error) {
  if (ledger)
    await writeFile(
      join(args.private, "public-failure.json"),
      JSON.stringify(
        failureReport(
          {
            mode: args.mode,
            role: args.role,
            production_head: args.head,
            harness_sha256: args.harness,
          },
          stage,
          trials,
          ledger.numeric(),
        ),
        null,
        2,
      ),
    );
  await writeFile(
    join(args.private, "failure-private.json"),
    JSON.stringify(
      {
        stage,
        error: String(error.stack ?? error),
        rows: ledger?.rows ?? [],
        events: ledger?.events ?? [],
        completed_trials: trials,
      },
      null,
      2,
    ),
  );
  console.error(JSON.stringify({ failed_stage: stage }));
  process.exitCode = 1;
} finally {
  ledger?.close();
  await context?.close();
  await browser.close();
}
