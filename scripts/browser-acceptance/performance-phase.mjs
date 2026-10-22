import assert from "node:assert/strict";

export const endpoints = Object.freeze({
  status: "/api/status",
  summary: "/api/dashboard/summary",
  workouts: "/api/dashboard/workouts",
  volume: "/api/dashboard/volume",
  steps: "/api/dashboard/steps",
  heart: "/api/dashboard/heart",
  sleep: "/api/dashboard/sleep",
  sleep_stages: "/api/dashboard/sleep/stages",
  capabilities: "/api/dashboard/capabilities",
});
const phases = ["mount", "toggle", "scope", "cached_chat", "cached_dashboard"];
const signature = (url) =>
  `${url.pathname}?${[...url.searchParams]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&")}`;
const endpointOf = (url) =>
  Object.keys(endpoints).find((key) => endpoints[key] === url.pathname) ??
  "other";
const failure = (row) =>
  row.transport_error !== null ||
  row.body_error !== null ||
  row.parse_error !== null ||
  (row.status !== null && row.status >= 400);

export function panelExpectations(
  phase,
  scope = {},
  granularity = "week",
  toggleCount = 1,
) {
  assert.ok(phases.includes(phase), "phase-name");
  assert.ok([1, 8].includes(toggleCount), "phase-toggle-count");
  const labels =
    phase === "cached_chat"
      ? []
      : phase === "toggle" && toggleCount === 1
        ? ["volume"]
        : Object.keys(endpoints).filter(
            (x) =>
              x !== "status" || ["mount", "cached_dashboard"].includes(phase),
          );
  return labels.map((endpoint) => ({
    endpoint,
    query:
      endpoint === "status"
        ? {}
        : {
            ...scope,
            ...(["steps", "sleep"].includes(endpoint)
              ? { granularity: "day" }
              : endpoint === "heart"
                ? { granularity: "week" }
                : endpoint === "volume"
                  ? { granularity }
                  : {}),
          },
  }));
}

// Document lifecycle networkidle is intentionally absent. Body delivery and UI
// application are separate barriers. Recheck exact counts after rendering too.
export async function settlePhase(_page, phase, rendered) {
  await phase.waitForBodies();
  phase.assertComplete();
  await rendered();
  phase.assertComplete();
}

export class RequestLedger {
  constructor(page, { timeout = 30000 } = {}) {
    this.page = page;
    this.timeout = timeout;
    this.rows = [];
    this.epoch = 0;
    this.current = null;
    this.events = [];
    this.requests = new Map();
    this.responses = new Map();
    this.listeners = new Set();
    this.handlers = {
      request: (request) => this.started(request),
      response: (response) => this.headers(response),
      requestfinished: (request) => {
        const row = this.requests.get(request);
        if (row) {
          row.body_complete = true;
          row.body_finished_at = Date.now();
          this.record("body_complete", row);
          this.changed();
        }
      },
      requestfailed: (request) => {
        const row = this.requests.get(request);
        if (row) {
          row.transport_error = request.failure()?.errorText ?? "unknown";
          row.failed_at = Date.now();
          this.record("transport_failed", row);
          this.changed();
        }
      },
    };
    for (const [name, handler] of Object.entries(this.handlers))
      page.on(name, handler);
  }
  begin(name, expected) {
    assert.ok(phases.includes(name), "phase-name");
    const phase = {
      name,
      epoch: ++this.epoch,
      expected: expected.map(({ endpoint, query }) => {
        assert.ok(Object.hasOwn(endpoints, endpoint), "phase-endpoint");
        const url = new URL(endpoints[endpoint], "http://synthetic");
        for (const [k, v] of Object.entries(query)) url.searchParams.set(k, v);
        return signature(url);
      }),
    };
    phase.assertComplete = () => this.assertPhase(phase);
    phase.waitForBodies = () => this.waitFor(phase);
    phase.bodies = async () =>
      Object.fromEntries(
        await Promise.all(
          this.phaseRows(phase).map(async (row) => [
            row.endpoint,
            await this.parsedBody(row),
          ]),
        ),
      );
    this.current = phase;
    return phase;
  }
  started(request) {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/") && url.pathname !== "/health") return;
    const row = {
      id: this.rows.length + 1,
      phase: this.current?.name ?? "unscoped",
      epoch: this.current?.epoch ?? 0,
      endpoint: endpointOf(url),
      panel:
        url.pathname.startsWith("/api/dashboard/") ||
        url.pathname === "/api/status",
      url: request.url(),
      signature: signature(url),
      method: request.method(),
      started_at: Date.now(),
      status: null,
      headers_at: null,
      body_complete: false,
      body_finished_at: null,
      finished_resolved: false,
      body_error: null,
      parse_error: null,
      transport_error: null,
      failed_at: null,
      cancellation_evidence: null,
    };
    this.rows.push(row);
    this.requests.set(request, row);
    this.record("request", row);
    this.changed();
  }
  headers(response) {
    const row = this.requests.get(response.request());
    if (!row) return;
    row.status = response.status();
    row.headers_at = Date.now();
    this.responses.set(row.id, response);
    this.record("headers", row);
    response.finished().then(
      (error) => {
        row.finished_resolved = true;
        if (error) row.body_error = String(error.message ?? error);
        this.record("body_result", row);
        this.changed();
      },
      (error) => {
        row.finished_resolved = true;
        row.body_error = String(error.message ?? error);
        this.record("body_result", row);
        this.changed();
      },
    );
    this.changed();
  }
  async parsedBody(row) {
    try {
      return await this.responses.get(row.id).json();
    } catch (error) {
      row.parse_error = String(error.message ?? error);
      this.record("parse_failed", row);
      throw error;
    }
  }
  record(event, row) {
    row.delivery_state = failure(row)
      ? "failed"
      : row.body_complete && row.finished_resolved
        ? "delivered"
        : "pending";
    this.events.push(
      Object.freeze({
        event,
        id: row.id,
        issuing_phase: row.phase,
        issuing_epoch: row.epoch,
        event_phase: this.current?.name ?? "unscoped",
        event_epoch: this.current?.epoch ?? 0,
        epoch_ms: Date.now(),
        status: row.status,
        delivery_state: row.delivery_state,
        body_complete: row.body_complete,
        transport_error: row.transport_error,
        body_error: row.body_error,
      }),
    );
  }
  phaseRows(phase) {
    return this.rows.filter((row) => row.epoch === phase.epoch && row.panel);
  }
  assertPhase(phase) {
    const rows = this.phaseRows(phase);
    assert.equal(
      rows.length,
      phase.expected.length,
      "phase-exact-request-count",
    );
    assert.deepEqual(
      rows.map((row) => row.signature).sort(),
      [...phase.expected].sort(),
      "phase-scope-or-generation-mismatch",
    );
    assert.ok(
      this.rows
        .filter((row) => row.panel)
        .every(
          (row) => row.body_complete && row.finished_resolved && !failure(row),
        ),
      "phase-pending-or-failed-panel",
    );
    assert.ok(
      rows.every(
        (row) =>
          row.method === "GET" &&
          row.status === 200 &&
          row.body_complete &&
          row.finished_resolved &&
          !failure(row),
      ),
      "phase-delivery-failed-or-pending",
    );
  }
  changed() {
    for (const check of [...this.listeners]) check();
  }
  waitFor(phase) {
    return new Promise((resolve, reject) => {
      const finish = (error) => {
        clearTimeout(timer);
        this.listeners.delete(check);
        if (error) reject(error);
        else resolve();
      };
      const check = () => {
        const rows = this.phaseRows(phase);
        if (
          this.rows.filter((row) => row.panel).some(failure) ||
          rows.length > phase.expected.length ||
          rows.some((row) => !phase.expected.includes(row.signature))
        )
          return finish(new Error("phase-request-failed-or-unexpected"));
        try {
          this.assertPhase(phase);
          finish();
        } catch {
          /* event or deadline will retry */
        }
      };
      const timer = setTimeout(
        () => finish(new Error("phase-body-deadline")),
        this.timeout,
      );
      this.listeners.add(check);
      check();
    });
  }
  // Classification is diagnostic. Even evidenced intentional cancels always
  // fail assertNormal and remain in raw/public aggregate counters.
  markIntentional(id, evidence) {
    const row = this.rows.find((item) => item.id === id);
    assert.ok(
      row?.transport_error === "net::ERR_ABORTED" &&
        !row.parse_error &&
        (!row.body_error ||
          row.body_error.includes("ERR_ABORTED") ||
          row.body_error.includes("AbortError")) &&
        (row.status === null || row.status < 400) &&
        evidence.signal_aborted === true &&
        evidence.action_observed === true,
      "cancellation-evidence-required",
    );
    assert.ok(
      ["volume_supersession", "dashboard_unmount"].includes(evidence.action),
      "cancellation-evidence-action",
    );
    if (evidence.action === "volume_supersession") {
      const next = this.rows.find((item) => item.id === evidence.superseded_by);
      assert.ok(
        row.endpoint === "volume" &&
          next?.endpoint === "volume" &&
          next.epoch > row.epoch &&
          next.signature !== row.signature,
        "cancellation-evidence-supersession",
      );
    }
    row.cancellation_evidence = { ...evidence };
  }
  assertIntentionalScenario() {
    assert.ok(
      this.rows.some((row) => row.cancellation_evidence),
      "unrelated-or-unproven-error",
    );
    assert.ok(
      this.rows.every(
        (row) =>
          !failure(row) ||
          (row.cancellation_evidence &&
            !row.parse_error &&
            (!row.body_error ||
              row.body_error.includes("ERR_ABORTED") ||
              row.body_error.includes("AbortError")) &&
            (row.status === null || row.status < 400) &&
            row.transport_error === "net::ERR_ABORTED"),
      ),
      "unrelated-or-unproven-error",
    );
  }
  assertNormal() {
    assert.ok(
      this.rows.every(
        (row) =>
          !failure(row) &&
          row.status !== null &&
          row.body_complete &&
          row.finished_resolved,
      ),
      "normal-scenario-error-or-incomplete-request",
    );
  }
  async drain() {
    const phase = { epoch: this.epoch };
    await new Promise((resolve, reject) => {
      const finish = (error) => {
        clearTimeout(timer);
        this.listeners.delete(check);
        if (error) reject(error);
        else resolve();
      };
      const check = () => {
        if (
          this.rows.every(
            (row) =>
              row.transport_error ||
              row.body_error ||
              (row.body_complete && row.finished_resolved),
          )
        )
          finish();
      };
      const timer = setTimeout(
        () => finish(new Error("ledger-body-deadline")),
        this.timeout,
      );
      this.listeners.add(check);
      check();
    });
    return phase;
  }
  numeric() {
    const result = {
      requests: this.rows.length,
      transport_failures: this.rows.filter((row) => row.transport_error).length,
      panel_transport_failures: this.rows.filter(
        (row) => row.transport_error && row.panel,
      ).length,
      http_failures: this.rows.filter(
        (row) => row.status !== null && row.status >= 400,
      ).length,
      body_failures: this.rows.filter((row) => row.body_error).length,
      parse_failures: this.rows.filter((row) => row.parse_error).length,
      aborts: this.rows.filter(
        (row) => row.transport_error === "net::ERR_ABORTED",
      ).length,
      network_failures: this.rows.filter(
        (row) =>
          row.transport_error &&
          !["net::ERR_ABORTED", "net::ERR_TIMED_OUT"].includes(
            row.transport_error,
          ),
      ).length,
      timeouts: this.rows.filter((row) =>
        row.transport_error?.includes("TIMED_OUT"),
      ).length,
      intentional_cancellations: this.rows.filter(
        (row) => row.cancellation_evidence,
      ).length,
      incomplete_bodies: this.rows.filter((row) => !row.body_complete).length,
      endpoints: Object.fromEntries(
        [...Object.keys(endpoints), "other"].map((name) => [
          name,
          this.rows.filter((row) => row.endpoint === name).length,
        ]),
      ),
    };
    validateNumeric(result);
    return result;
  }
  close() {
    for (const [name, handler] of Object.entries(this.handlers))
      this.page.off(name, handler);
  }
}

export function validateNumeric(value) {
  const keys = [
    "requests",
    "transport_failures",
    "panel_transport_failures",
    "http_failures",
    "body_failures",
    "parse_failures",
    "aborts",
    "network_failures",
    "timeouts",
    "intentional_cancellations",
    "incomplete_bodies",
    "endpoints",
  ];
  assert.deepEqual(
    Object.keys(value).sort(),
    [...keys].sort(),
    "numeric-closed-keys",
  );
  assert.deepEqual(
    Object.keys(value.endpoints).sort(),
    [...Object.keys(endpoints), "other"].sort(),
    "numeric-closed-endpoints",
  );
  for (const [key, n] of Object.entries(value))
    if (key !== "endpoints")
      assert.ok(Number.isInteger(n) && n >= 0, "numeric-count");
  assert.ok(
    Object.values(value.endpoints).every((n) => Number.isInteger(n) && n >= 0),
    "numeric-endpoint-count",
  );
  return value;
}

export function canonicalBase(value) {
  const url = new URL(value);
  assert.ok(
    url.protocol === "http:" &&
      ["localhost", "127.0.0.1"].includes(url.hostname) &&
      url.pathname === "/" &&
      !url.search &&
      !url.hash &&
      !url.username &&
      !url.password,
    "loopback-root-required",
  );
  return url.origin;
}
