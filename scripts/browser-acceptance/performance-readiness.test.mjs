import assert from "node:assert/strict";
import { test } from "node:test";
import { settlePhase } from "./performance-phase.mjs";

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
};
const tick = () => new Promise(setImmediate);

test("already-reached document networkidle cannot settle eight active panel bodies", async () => {
  const bodies = deferred();
  const render = deferred();
  let delivered = 0;
  let rendered = false;
  let settled = false;
  const oldDocument = { waitForLoadState: async () => {} };
  const phase = {
    waitForBodies: () => bodies.promise,
    assertComplete: () => assert.equal(delivered, 8),
  };
  const operation = settlePhase(oldDocument, phase, async () => {
    await render.promise;
    assert.equal(rendered, true);
  }).then(() => {
    settled = true;
  });
  await tick();
  assert.equal(
    settled,
    false,
    "old networkidle returned with all eight panel bodies still pending",
  );
  delivered = 8;
  bodies.resolve();
  await tick();
  assert.equal(
    settled,
    false,
    "body completion must not imply rendered readiness",
  );
  rendered = true;
  render.resolve();
  await operation;
  assert.equal(settled, true);
});

test("delivered responses cannot settle before corresponding rendered panels", async () => {
  const render = deferred();
  let rendered = false;
  let settled = false;
  const phase = { waitForBodies: async () => {}, assertComplete: () => {} };
  const operation = settlePhase(
    { waitForLoadState: async () => {} },
    phase,
    () =>
      render.promise.then(() => {
        rendered = true;
      }),
  ).then(() => {
    settled = true;
  });
  await tick();
  assert.equal(
    settled,
    false,
    "historical document wait skipped rendered readiness",
  );
  render.resolve();
  await operation;
  assert.equal(rendered, true);
});
