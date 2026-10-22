import assert from "node:assert/strict";
import { test } from "node:test";
import { canonicalBase } from "./performance-phase.mjs";
test("the actual initial control request uses a single slash with or without a trailing base slash", () => {
  for (const raw of ["http://127.0.0.1:1234", "http://127.0.0.1:1234/"])
    assert.equal(
      canonicalBase(raw) + "/__performance/reset",
      "http://127.0.0.1:1234/__performance/reset",
    );
});
