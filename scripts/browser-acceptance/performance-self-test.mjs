import assert from "node:assert/strict";
import { createServer } from "node:http";
import { chromium } from "playwright";
import {
  RequestLedger,
  endpoints,
  panelExpectations,
  settlePhase,
} from "./performance-phase.mjs";
import {
  capturePreviousCanvases,
  waitForRenderedPanels,
} from "./performance-render.mjs";

const titles = {
  summary: "Activity Rings",
  workouts: "Recent Workouts",
  volume: "Training Volume",
  steps: "Daily Steps",
  heart: "Resting Heart Rate",
  sleep: "Sleep Interval Coverage",
  sleep_stages: "Measured Sleep Stages",
  capabilities: "Data Sources",
};
const html = `<!doctype html><body><p id="loading">Pending panels</p><script>
window.controllers=[];
window.start=(urls)=>{window.sent=true;return urls.map(url=>{const controller=new AbortController();window.controllers.push(controller);return fetch(url,{signal:controller.signal}).then(r=>r.json()).catch(e=>({error:e.name}))})};
window.paint=()=>{document.body.innerHTML=${JSON.stringify(
  Object.entries(titles)
    .map(
      ([key, title]) =>
        `<section><h2>${title}</h2>${["volume", "steps", "heart", "sleep"].includes(key) ? '<canvas width="10" height="10"></canvas>' : ""}${key === "workouts" ? "No workouts match this scope" : key === "capabilities" || key === "summary" ? "No data" : key === "sleep_stages" ? "Synthetic no stages" : ""}${key === "volume" ? '<button aria-pressed="true">week</button>' : ""}</section>`,
    )
    .join(""),
)}};
</script>`;
let release = false;
const pending = [];
function body(path) {
  if (path.endsWith("/summary")) return { days: [] };
  if (path.endsWith("/sleep/stages"))
    return {
      stage_data_available: false,
      stages_hours: {},
      message: "Synthetic no stages",
    };
  if (path.endsWith("/volume")) return { series: [{}] };
  if (["/steps", "/heart", "/sleep"].some((x) => path.endsWith(x)))
    return { series: [{ value: 1 }] };
  if (path.endsWith("/workouts")) return { workouts: [] };
  if (path.endsWith("/capabilities")) return { capabilities: [] };
  return {};
}
const server = createServer((req, res) => {
  const url = new URL(req.url, "http://synthetic");
  if (url.pathname === "/") {
    res.end(html);
    return;
  }
  if (url.pathname === "/api/settings") {
    res.writeHead(500, { "content-type": "application/json" });
    res.end("{}");
    return;
  }
  const finish = () => res.end(JSON.stringify(body(url.pathname)));
  res.writeHead(200, { "content-type": "application/json" });
  res.flushHeaders();
  if (release) finish();
  else pending.push(finish);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch(
  process.env.TTI_BROWSER_CHANNEL
    ? { channel: process.env.TTI_BROWSER_CHANNEL }
    : {},
);
try {
  const page = await browser.newPage();
  const ledger = new RequestLedger(page);
  await page.goto(base);
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => window.paint());
  const phase = ledger.begin("scope", panelExpectations("scope", {}, "week"));
  await capturePreviousCanvases(page);
  await page.evaluate(
    (urls) => {
      window.start(urls);
    },
    phase.expected.map((signature) => signature.replace(/\?$/, "")),
  );
  let complete = false;
  const ready = (
    process.argv.includes("--historical-wait")
      ? async (page) => page.waitForLoadState("networkidle")
      : settlePhase
  )(page, phase, () => waitForRenderedPanels(page, phase)).then(() => {
    complete = true;
  });
  await page.waitForFunction(() => window.controllers.length === 8);
  assert.equal(complete, false);
  release = true;
  pending.splice(0).forEach((fn) => fn());
  await phase.waitForBodies();
  assert.equal(
    complete,
    false,
    "bodies alone cannot complete the render barrier",
  );
  await page.evaluate(() => window.paint());
  await ready;
  ledger.assertNormal();
  assert.equal(ledger.phaseRows(phase).length, 8);
  ledger.close();
  await page.close();

  // Actual aborted browser body, explicit superseding action and observed signal.
  release = false;
  const cancelPage = await browser.newPage();
  const cancels = new RequestLedger(cancelPage);
  await cancelPage.goto(base);
  cancels.begin("mount", [
    { endpoint: "volume", query: { granularity: "week" } },
  ]);
  await cancelPage.evaluate(() => {
    window.start(["/api/dashboard/volume?granularity=week"]);
  });
  await cancelPage.waitForFunction(() => window.controllers.length === 1);
  cancels.begin("toggle", [
    { endpoint: "volume", query: { granularity: "month" } },
  ]);
  await cancelPage.evaluate(() => {
    window.controllers[0].abort();
    window.supersessionObserved = true;
    window.start(["/api/dashboard/volume?granularity=month"]);
  });
  release = true;
  pending.splice(0).forEach((fn) => fn());
  await cancels.drain();
  const observed = await cancelPage.evaluate(() => ({
    signal_aborted: window.controllers[0].signal.aborted,
    action_observed: window.supersessionObserved,
  }));
  cancels.markIntentional(1, {
    action: "volume_supersession",
    ...observed,
    superseded_by: 2,
  });
  cancels.assertIntentionalScenario();
  assert.throws(() => cancels.assertNormal(), /normal/);
  assert.equal(cancels.numeric().transport_failures, 1);
  await cancelPage.evaluate(() => fetch("/api/settings").then((r) => r.text()));
  await cancels.drain();
  assert.equal(cancels.numeric().http_failures, 1);
  assert.throws(() => cancels.assertIntentionalScenario(), /unrelated/);
  // A synthetic timeout is transport failure, not HTTP 500 or intentional abort.
  await cancelPage.route("**/api/settings?timeout=1", (route) =>
    route.abort("timedout"),
  );
  await cancelPage.evaluate(() =>
    fetch("/api/settings?timeout=1").catch(() => {}),
  );
  await cancels.drain();
  assert.equal(cancels.numeric().timeouts, 1);
  assert.throws(() => cancels.assertNormal(), /normal/);
  cancels.close();
  await cancelPage.close();
  release = false;
  const leavePage = await browser.newPage();
  const leaving = new RequestLedger(leavePage);
  await leavePage.goto(base);
  leaving.begin("scope", panelExpectations("scope"));
  await leavePage.evaluate(
    (urls) => {
      window.start(urls);
    },
    Object.values(endpoints).filter((p) => p !== "/api/status"),
  );
  await leavePage.waitForFunction(() => window.controllers.length === 8);
  await leavePage.evaluate(() => {
    window.controllers.forEach((c) => c.abort());
    window.unmountObserved = true;
    document.body.innerHTML = '<textarea aria-label="Chat input"></textarea>';
  });
  await leaving.drain();
  const leaveEvidence = await leavePage.evaluate(() => ({
    action_observed: window.unmountObserved,
    signals: window.controllers.map((c) => c.signal.aborted),
  }));
  for (const [i, row] of leaving.rows.entries())
    leaving.markIntentional(row.id, {
      action: "dashboard_unmount",
      action_observed: leaveEvidence.action_observed,
      signal_aborted: leaveEvidence.signals[i],
    });
  leaving.assertIntentionalScenario();
  assert.throws(() => leaving.assertNormal(), /normal/);
  assert.equal(leaving.numeric().transport_failures, 8);
  assert.ok(await leavePage.getByLabel("Chat input").isEnabled());
  release = true;
  pending.splice(0).forEach((fn) => fn());
  leaving.close();
  await leavePage.close();
  console.log(
    JSON.stringify({
      chatUnmountAbortLedger: true,
      bodyAndRenderedBarrier: true,
      exactEight: true,
      explicitSupersession: true,
      rawAbortRetained: true,
      http500Rejected: true,
      transportTimeoutRejected: true,
      normalZeroErrorsPreserved: true,
    }),
  );
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
