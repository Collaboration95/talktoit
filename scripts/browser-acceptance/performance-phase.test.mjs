import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import {
  RequestLedger,
  panelExpectations,
  validateNumeric,
} from "./performance-phase.mjs";

const tick = () => new Promise(setImmediate);
function fixture() {
  const page = new EventEmitter();
  const ledger = new RequestLedger(page);
  const request = (url) => ({
    url: () => `http://127.0.0.1:8000${url}`,
    method: () => "GET",
    failure: () => ({ errorText: "net::ERR_ABORTED" }),
  });
  function headers(req, status = 200) {
    let finish;
    const body = new Promise((resolve) => {
      finish = resolve;
    });
    page.emit("response", {
      request: () => req,
      status: () => status,
      finished: () => body,
    });
    return () => {
      finish(null);
      page.emit("requestfinished", req);
    };
  }
  return { page, ledger, request, headers };
}
const one = (query = {}) => [{ endpoint: "volume", query }];

test("headers are not body completion; exact query scope and epoch bind late events", async () => {
  const { page, ledger, request, headers } = fixture();
  const old = ledger.begin("mount", one({ granularity: "week" }));
  const first = request("/api/dashboard/volume?granularity=week");
  page.emit("request", first);
  const finishOld = headers(first);
  const next = ledger.begin(
    "scope",
    one({ start: "2024-01-01", end: "2024-01-07", granularity: "week" }),
  );
  let settled = false;
  const waiting = next.waitForBodies().then(() => {
    settled = true;
  });
  finishOld();
  await tick();
  assert.equal(settled, false);
  assert.equal(ledger.rows[0].epoch, old.epoch);
  const event = ledger.events.find(
    (e) => e.id === 1 && e.event === "body_complete",
  );
  assert.equal(event.issuing_phase, "mount");
  assert.equal(event.event_phase, "scope");
  const current = request(
    "/api/dashboard/volume?end=2024-01-07&granularity=week&start=2024-01-01",
  );
  page.emit("request", current);
  const finishCurrent = headers(current);
  await tick();
  assert.equal(settled, false);
  finishCurrent();
  await waiting;
  next.assertComplete();
  assert.equal(ledger.rows[1].epoch, next.epoch);
  ledger.assertNormal();
  ledger.close();
});

test("wrong date/type/source, cursor, duplicates or unexpected endpoints cannot satisfy a phase", async () => {
  for (const suffix of [
    "start=2024-01-02",
    "start=2024-01-01&source=other",
    "start=2024-01-01&activity_type=other",
    "start=2024-01-01&cursor=next",
  ]) {
    const { page, ledger, request, headers } = fixture();
    const phase = ledger.begin("scope", one({ start: "2024-01-01" }));
    const req = request(`/api/dashboard/volume?${suffix}`);
    page.emit("request", req);
    headers(req)();
    await tick();
    assert.throws(() => phase.assertComplete(), /phase/);
    ledger.close();
  }
  const { page, ledger, request, headers } = fixture();
  const phase = ledger.begin("toggle", one({ granularity: "month" }));
  for (let i = 0; i < 2; i++) {
    const r = request("/api/dashboard/volume?granularity=month");
    page.emit("request", r);
    headers(r)();
  }
  await tick();
  assert.throws(() => phase.assertComplete(), /phase/);
  ledger.close();
});

test("HTTP 500 and actual transport timeout remain errors even with completed bodies", async () => {
  const { page, ledger, request, headers } = fixture();
  ledger.begin("mount", one());
  const bad = request("/api/dashboard/volume");
  page.emit("request", bad);
  headers(bad, 500)();
  const timeout = request("/api/settings");
  timeout.failure = () => ({ errorText: "net::ERR_TIMED_OUT" });
  page.emit("request", timeout);
  page.emit("requestfailed", timeout);
  await tick();
  assert.throws(() => ledger.assertNormal(), /normal/);
  const numeric = ledger.numeric();
  assert.equal(numeric.http_failures, 1);
  assert.equal(numeric.transport_failures, 1);
  assert.equal(numeric.timeouts, 1);
  assert.equal(ledger.rows[0].body_complete, true);
  assert.equal(ledger.rows[1].transport_error, "net::ERR_TIMED_OUT");
  ledger.close();
});

test("supersession classification needs explicit signal/action evidence and never clears the raw count", async () => {
  const { page, ledger, request, headers } = fixture();
  ledger.begin("mount", one({ granularity: "week" }));
  const old = request("/api/dashboard/volume?granularity=week");
  page.emit("request", old);
  page.emit("requestfailed", old);
  const row = ledger.rows[0];
  assert.throws(
    () =>
      ledger.markIntentional(row.id, {
        action: "volume_supersession",
        signal_aborted: false,
      }),
    /evidence/,
  );
  ledger.begin("toggle", one({ granularity: "month" }));
  const next = request("/api/dashboard/volume?granularity=month");
  page.emit("request", next);
  headers(next)();
  await tick();
  ledger.markIntentional(row.id, {
    action: "volume_supersession",
    signal_aborted: true,
    action_observed: true,
    superseded_by: ledger.rows[1].id,
  });
  assert.equal(ledger.numeric().transport_failures, 1);
  assert.equal(ledger.numeric().intentional_cancellations, 1);
  assert.throws(() => ledger.assertNormal(), /normal/);
  ledger.assertIntentionalScenario();
  const unrelated = request("/api/settings");
  page.emit("request", unrelated);
  headers(unrelated, 500)();
  await tick();
  assert.throws(() => ledger.assertIntentionalScenario(), /unrelated/);
  ledger.close();
});

test("unmount cancellation is distinct from an unexplained ERR_ABORTED and from network failure", async () => {
  const { page, ledger, request } = fixture();
  ledger.begin("scope", one());
  const r = request("/api/dashboard/volume");
  page.emit("request", r);
  page.emit("requestfailed", r);
  assert.throws(() => ledger.assertIntentionalScenario(), /unrelated/);
  ledger.markIntentional(1, {
    action: "dashboard_unmount",
    signal_aborted: true,
    action_observed: true,
  });
  ledger.assertIntentionalScenario();
  assert.throws(() => ledger.assertNormal(), /normal/);
  const network = request("/api/settings");
  network.failure = () => ({ errorText: "net::ERR_CONNECTION_RESET" });
  page.emit("request", network);
  page.emit("requestfailed", network);
  assert.throws(
    () =>
      ledger.markIntentional(2, {
        action: "dashboard_unmount",
        signal_aborted: true,
        action_observed: true,
      }),
    /evidence/,
  );
  assert.throws(() => ledger.assertIntentionalScenario(), /unrelated/);
  ledger.close();
});

test("normal ledger includes Chat-return failures before the next dashboard phase", async () => {
  const { page, ledger, request } = fixture();
  ledger.begin("cached_chat", []);
  const r = request("/api/dashboard/workouts");
  page.emit("request", r);
  page.emit("requestfailed", r);
  ledger.begin("cached_dashboard", []);
  assert.equal(ledger.rows[0].phase, "cached_chat");
  assert.equal(ledger.numeric().panel_transport_failures, 1);
  assert.throws(() => ledger.assertNormal(), /normal/);
  ledger.close();
});

test("public numeric payload is closed and cannot publish URLs, health values, question text, SQL or paths", () => {
  const { ledger } = fixture();
  const payload = ledger.numeric();
  validateNumeric(payload);
  for (const key of ["url", "question", "sql", "path", "rows", "generation_id"])
    assert.throws(
      () => validateNumeric({ ...payload, [key]: "private" }),
      /numeric/,
    );
  assert.throws(
    () =>
      validateNumeric({
        ...payload,
        endpoints: { ...payload.endpoints, "/private": 1 },
      }),
    /numeric/,
  );
  ledger.close();
});

test("portable phase expectations preserve exact 9/1/8 and explicit reference toggle 8", () => {
  assert.equal(panelExpectations("mount", {}, "week").length, 9);
  assert.equal(panelExpectations("toggle", {}, "month", 1).length, 1);
  assert.equal(panelExpectations("toggle", {}, "month", 8).length, 8);
  assert.equal(
    panelExpectations(
      "scope",
      { start: "2024-01-01", end: "2024-01-07" },
      "month",
    ).length,
    8,
  );
});

test("an HTTP error on an aborted request cannot be reclassified as intentional", async () => {
  for (const status of [404, 500]) {
    const { page, ledger, request, headers } = fixture();
    ledger.begin("scope", one());
    const r = request("/api/dashboard/volume");
    page.emit("request", r);
    headers(r, status);
    page.emit("requestfailed", r);
    assert.throws(
      () =>
        ledger.markIntentional(1, {
          action: "dashboard_unmount",
          signal_aborted: true,
          action_observed: true,
        }),
      /evidence/,
    );
    ledger.close();
  }
});

test("an unrecognized extra dashboard endpoint fails the exact phase contract", async () => {
  const { page, ledger, request, headers } = fixture();
  const phase = ledger.begin("cached_chat", []);
  const r = request("/api/dashboard/unexpected");
  page.emit("request", r);
  headers(r)();
  await tick();
  assert.throws(() => phase.assertComplete(), /phase/);
  ledger.close();
});

test("invalid JSON is a retained parse failure, not a delivered successful phase", async () => {
  const { page, ledger, request } = fixture();
  const phase = ledger.begin("scope", one());
  const r = request("/api/dashboard/volume");
  page.emit("request", r);
  page.emit("response", {
    request: () => r,
    status: () => 200,
    finished: async () => null,
    json: async () => {
      throw new SyntaxError("synthetic invalid JSON");
    },
  });
  page.emit("requestfinished", r);
  await tick();
  await assert.rejects(() => phase.bodies(), /synthetic invalid JSON/);
  assert.throws(() => ledger.assertNormal(), /normal/);
  ledger.close();
});
