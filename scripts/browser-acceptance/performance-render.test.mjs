import assert from "node:assert/strict";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { settlePhase } from "./performance-phase.mjs";
import { waitForRenderedPanels } from "./performance-render.mjs";

const tick = () => new Promise(setImmediate);
const canvas = (width = 100, height = 100, layout = { width, height }) => ({
  width,
  height,
  getBoundingClientRect: () => layout,
});

function fixture(canvases, old = [], empty = false) {
  const state = {
    canvases,
    text: empty ? "Activity Rings No data" : "Activity Rings",
  };
  const section = {
    get textContent() {
      return state.text;
    },
    querySelector: (selector) =>
      selector === "h2"
        ? { textContent: "Activity Rings" }
        : selector === "canvas"
          ? (state.canvases[0] ?? null)
          : null,
    querySelectorAll: (selector) =>
      selector === "canvas" ? state.canvases : [],
  };
  const context = {
    document: {
      body: { textContent: "Activity Rings" },
      querySelector: () => null,
      querySelectorAll: () => [section],
    },
    window: { __ttiPreviousCanvases: new WeakSet(old) },
    location: { search: "" },
  };
  let poll;
  const page = {
    waitForFunction: (predicate, args) =>
      new Promise((resolve) => {
        const callback = runInNewContext(`(${predicate.toString()})`, context);
        poll = () => {
          if (callback(args)) resolve();
        };
        poll();
      }),
  };
  let bodiesDone;
  let delivered = false;
  const body = new Promise((resolve) => {
    bodiesDone = () => {
      delivered = true;
      resolve();
    };
  });
  const phase = {
    waitForBodies: () => body,
    assertComplete: () => assert.equal(delivered, true),
    bodies: async () => ({ summary: { days: empty ? [] : [{}] } }),
  };
  let settled = false;
  const result = settlePhase(page, phase, () =>
    waitForRenderedPanels(page, phase),
  ).then(() => {
    settled = true;
  });
  return {
    state,
    deliver: bodiesDone,
    poll: () => poll(),
    settled: () => settled,
    result,
  };
}

const previous = canvas();
for (const [name, canvases, old] of [
  ["absent", [], []],
  ["zero intrinsic size", [canvas(0, 0)], []],
  ["zero layout size", [canvas(100, 100, { width: 0, height: 0 })], []],
  ["previous-phase canvas", [previous], [previous]],
  ["fresh canvas alongside a zero canvas", [canvas(), canvas(0, 0)], []],
  [
    "fresh canvas alongside a previous canvas",
    [canvas(), previous],
    [previous],
  ],
]) {
  test(`nonempty summary stays pending after body delivery with ${name}`, async () => {
    const f = fixture(canvases, old);
    await tick();
    assert.equal(f.settled(), false, "body barrier must run first");
    f.deliver();
    await tick();
    assert.equal(
      f.settled(),
      false,
      `${name} must not satisfy current render readiness`,
    );
    f.state.canvases = [canvas(), canvas()];
    f.poll();
    await f.result;
    assert.equal(
      f.settled(),
      true,
      "all fresh nonzero canvases complete the same pending operation",
    );
  });
}

test("a nonempty summary with all fresh nonzero canvases completes after body delivery", async () => {
  const f = fixture([canvas(), canvas()]);
  f.deliver();
  await f.result;
  assert.equal(f.settled(), true);
});

test("valid empty summary still completes without any canvas", async () => {
  const f = fixture([], [], true);
  await tick();
  assert.equal(f.settled(), false);
  f.deliver();
  await f.result;
  assert.equal(f.settled(), true);
});
