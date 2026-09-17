# Planning, tools, and the provider boundary (LLM-*)

Scope: `backend/app/llm/` — the deterministic local planner, follow-up
resolution, tool dispatch, the provider gateway and its cache, the LiteRT-LM
lifecycle manager, the OpenAI client factory, the egress projections, and the
semantic-candidate verifier. The benchmark harness in `backend/app/bench/` is
covered here too because it feeds the same diagnostics channel.

The deterministic planner is the privacy boundary: a question it recognises
never leaves the machine. Most findings below are about that boundary being
wrong about what the user asked, rather than about egress.

---

## LLM-1 — "last year" resolves to the current year-to-date; any sentence containing "year" matches

**Medium** — `backend/app/llm/local_planner.py:51-52` (period handling at `:36-53`)

`_period_for_question` ends with `if "this year" in lower or "year" in lower:`
and returns `date(as_of.year, 1, 1)` through the dataset's latest date. Two
problems share that line. First, "last year" never reaches the earlier branches
— there is no `last year` case at all — so it silently means "this year so far".
Second, the bare `"year"` test is a substring check, so any sentence containing
the word, such as "how many years of data do I have", selects the year period.
The same function has no `this week` branch even though `last week` exists, so
period handling is asymmetric between a period and its named counterpart.

**Impact.** The user asks for the previous calendar year and receives a
six-month year-to-date series labelled only by the bucketed dates. Nothing in
the response says the period was substituted, so the answer looks correct.
Because the same `period` value also feeds the ranking and last-workout
branches, a phrase like "my longest run this year" is computed over the right
window by accident, while "my longest run last year" gets the wrong one.

**Evidence.** `audit/repro/tti_plan3.py` with a synthetic profile whose latest
date is 2026-06-30:

```
'resting heart rate last year'
  -> {..., "start_date": "2026-01-01", "end_date": "2026-06-30"}
'resting heart rate last month'
  -> {..., "start_date": "2026-05-01", "end_date": "2026-05-31"}
```

The month form behaves correctly, which is what makes the year form
plausible-looking: both are wired the same way and only one was implemented.

**Fix.** Match period words with word boundaries and add explicit cases:
`last year` → `date(as_of.year - 1, 1, 1)` to `date(as_of.year - 1, 12, 31)`,
`this year`/`year to date` → current behaviour. Consider returning a labelled
period and having the trend branch pick a granularity that keeps the bucket
count bounded (a six-month daily series is 180 points; the current code always
asks for `week`).

---

## LLM-2 — Activity detection is unanchored substring matching, so non-workout questions get workout answers

**Medium** — `backend/app/llm/local_planner.py:16-24` (duplicate at
`backend/app/llm/followups.py:100-107`; consumers at `local_planner.py:109-134`)

`_activity_type` tests `"run" in lower`, `"cycl" in lower`, `"bike" in lower`,
and the strength words against the raw sentence. "run" occurs inside *brunch*,
*running late*, and *genre*; "cycl" occurs inside *cyclone* and *recycle*;
"weight" occurs in questions about body weight rather than weights training.
Once an activity type is detected, the ranking branch (`top`, `longest`,
`highest heart`) or the recency branch (`last`, `latest`, `most recent`)
produces a complete, confident workout answer from the local database. The same
word lists are copy-pasted into `followups.py`, so any fix has to be applied
twice.

**Impact.** A question that has nothing to do with workouts is answered with a
workout card and a narrative, and the user has no signal that the question was
misread. It also spends a database query and, if the question had been
unrecognised, would have gone to the remote planner instead — so the false
positive is also a silent behaviour change in the opposite direction of the
privacy design.

**Evidence.** `audit/repro/tti_plan3.py`:

```
'Show my top brunch runs'   -> {"tool_name": "get_top_workouts", "arguments": {"activity_type": "Running", "metric": "duration", "n": 5}}
'Show my last brunch'       -> {"tool_name": "get_last_workout", "arguments": {"activity_type": "Running"}}
'my longest cyclone ride'   -> {"tool_name": "get_top_workouts", "arguments": {"activity_type": "Cycling", "metric": "duration", "n": 5}}
```

**Fix.** Match whole words (`re.search(r"\b(run|jog|jogging)\b", lower)`) and
require an activity phrase to sit next to a workout word ("run", "ride",
"session", "workout") before choosing a tool. Extract the vocabulary into one
shared module used by both planners.

---

## LLM-3 — The comparison planner accepts the word "week" but always compares calendar months

**Medium** — `backend/app/llm/local_planner.py:87-88` (plan builder at `:56-70`)

The trigger is `"compare" in lower and ("month" in lower or "week" in lower)`,
which advertises week support, but `_comparison_plan` unconditionally computes
`_month_bounds(as_of)` for the current period and `_month_bounds(start - 1 day)`
for the prior one. There is no week branch anywhere in the file, and the only
week-aware code is the `last week` case in `_period_for_question`, which the
comparison branch does not call.

**Impact.** "Compare my runs this week and last week" returns June 2026 versus
May 2026 — correct-looking labels, wrong periods, no warning. Because the
comparison template renders the labels it is handed, the user sees month names
in the answer to a week question and may still not notice.

**Evidence.** `audit/repro/tti_plan3.py`:

```
'compare my runs this week and last week'
  -> {"tool_name": "get_comparison", "arguments": {"this_start": "2026-06-01", "this_end": "2026-06-30",
      "last_start": "2026-05-01", "last_end": "2026-05-31", "this_label": "June 2026", "last_label": "May 2026"}}
```

The month-worded control question produces byte-identical arguments, confirming
the week wording is ignored rather than mis-parsed.

**Fix.** Branch on the granularity word inside `_comparison_plan`: weeks use the
Monday-based window from `_period_for_question`, and labels should be date
ranges. Add a test per granularity; the current tests cover the month path only.

---

## LLM-4 — Every cache miss re-reads and re-parses the whole conversation to build follow-up contexts

**Medium** — `backend/app/api/chat.py:181-221` (loader at
`backend/app/state/app_state.py:616-626`)

When the exact and canonical caches miss, `_prepare_chat` calls
`repository.get_turns(...)`, which is `SELECT * FROM turns WHERE
conversation_id = ? ORDER BY ordinal` — every column, including the full
`response_json` envelope of every prior answer. The rows are then walked to
`json.loads` each `canonical_plan_json` and build `FollowupContext` objects. Only
the plan and question fields are used; the envelopes are discarded. The cost
grows with conversation length and is paid on every miss, including the common
case of asking a brand-new question in a long conversation. The sibling loader
`semantic_turns` deliberately selects only the fields it needs and documents
why, so the pattern exists in the codebase and was not applied here.

There is a second, smaller problem in the same block: `resolve_followup`
proceeds only when exactly one context matches the active dataset, so once a
conversation contains two answered turns, every supported reference ("group
that by week", "compare to the prior period") becomes a disambiguation prompt
unless the user's wording keeps it unique. The `label` field carried on each
context is then only used to render the choice list, and the singular "that"
that users write to mean "the result I just got" is not resolvable.

**Impact.** Long conversations get slower on every uncached question, in
proportion to how much data the transcript already holds. Follow-up references
degrade to a question-instead-of-an-answer exactly when history gets long
enough to be useful.

**Fix.** Add a plan-only loader (or extend `semantic_turns` with a
conversation-scoped variant) that selects `id, question, canonical_plan_json,
created_at` and filters to completed turns. If the singleton rule is meant to
relax, prefer the most recent context and use the ordinal to say so in the
disambiguation text.

---

## LLM-5 — The gateway cache and circuit-breaker state are shared mutable state with no lock or drain

**Medium** — `backend/app/llm/provider_gateway.py:229-270`, `:171-186`,
`:278-285` (shutdown path in `backend/app/main.py:158-186`)

`_gateway_cache` is a module-level dict; `get_gateway_for_config` does an
unlocked get, constructs a new `AsyncOpenAI` (and its connection pool) on a
miss, and stores it. Two concurrent first requests for the same config can both
miss, and one of the two clients is then unreachable and never closed. Entries
are keyed on provider, mode, model, and base URL, so changing any setting in
the UI leaves the previous client alive for the process lifetime; there is no
eviction path other than shutdown. The circuit-breaker counters
(`_consecutive_failures`, `_circuit_open_until`) are mutated from the event loop
without a lock, which is benign for `+= 1` under asyncio's cooperative
scheduling but becomes wrong the moment any caller reaches the gateway from a
worker thread.

At shutdown, `aclose_all_gateways` closes every cached client immediately. The
lifespan calls it in the `finally` block of the app, after the ASGI server has
stopped accepting new work but potentially while a request that is already
inside `complete()` is awaiting a response; closing the underlying client
mid-call turns that in-flight answer into a transport error. The lifespan then
closes `app.state.provider_gateway` a second time (idempotent for httpx, so
harmless but redundant, and the duplicated nested `try` blocks at
`main.py:159-186` make the intent hard to read).

**Impact.** A provider setting change leaks one HTTP client per change; a
shutdown race can fail an answer that was seconds from completing; a
double-constructed client wastes a connection pool in tests that exercise
concurrent first use.

**Fix.** Guard the cache with an `asyncio.Lock` (or key the check and the
construction together), close evicted entries when a key is replaced, and give
`aclose_all_gateways` a quiet-period or in-flight counter before closing.

---

## LLM-6 — LiteRT lifecycle: a binary that does not exist reports as available, and `stop()` kills a pid it does not own

**Low** — `backend/app/llm/litert.py:69-85`, `:272-280` (kill at `:330-339`)

`resolve_litert_binary` takes the first token of `LITERT_SERVE_CMD` and returns
it. The branch that would distinguish a real binary from a missing one returns
the same value either way, so the existence check is dead code and
`status()["binary_available"]` is `True` for a path that does not exist.

```
$ LITERT_SERVE_CMD="/nonexistent/litert-lm serve --port 9999" ./backend/.venv/bin/python -c \
  "import sys; sys.path.insert(0,'backend'); from app.llm import litert; print(litert.resolve_litert_binary(), litert.status()['binary_available'])"
/nonexistent/litert-lm True
```

`start()` spawns the process, then writes the pidfile; if the write fails it
returns `started: False` while leaving the just-spawned server running with no
pidfile, so `stop()` can never find it and the process survives until something
else kills it. `stop()` sends `SIGTERM` and then `SIGKILL` to whatever pid the
pidfile holds, with no check that the process is the `litert-lm serve` this app
launched; a pidfile left over after a reboot, or a recycled pid, is a kill of an
unrelated process. The docstring claims the opposite ("Never kills an unrelated
process"). The pidfile also has a read-then-write window between `status()` and
`pidfile.write_text`, so two starts that pass the `running` check can both
spawn, with the second write orphaning the first process.

**Impact.** The settings screen shows LiteRT as installed when it is not, so
the first Start produces a confusing FileNotFoundError string instead of an
install hint. The orphaned-server case leaves a model server holding memory with
no UI path to stop it, and the kill path is a small but real safety problem on
a shared machine.

**Fix.** Return `None` from the override branch when neither `Path(...).exists()`
nor `shutil.which(...)` succeeds. Verify ownership before signalling by
matching the process command line (or record the pid and start time together in
the pidfile). Take an exclusive lock file around the start/stop pair, and on a
pidfile write failure terminate the process that was just spawned.

---

## LLM-7 — Display formatting is done by unanchored `str.replace` inside tool dispatch, and the fallback tool forwards unvalidated model text

**Low** — `backend/app/llm/tools.py:280-282`, `:365-368`, `:371-386`
(`get_fallback` at `backend/app/db/queries.py:867-882`)

`_tool_get_top_workouts` and `_tool_get_comparison` rewrite the payload they
just built with `title.replace(activity_type, display_activity_type(activity_type))`
and the same on each row label. That is presentation work in the data layer: it
mutates the payload the renderer receives, uses an unanchored replace that hits
every occurrence including inside other words, and silently does nothing when
the resolved value is not literally present. `resolve_activity_type`
(`backend/app/db/data_profile.py:79-92`) returns the requested string unchanged
when no stored type matches, so a V2 database with the empty-`activity_type`
problem from ING-1, or a stored id such as `HKWorkoutActivityTypeRunning`, can
surface the raw identifier in a title with no display conversion.

`_tool_get_fallback_answer` takes `args.get("text", "")` straight from the
model and passes it to `queries.get_fallback`, which stores it verbatim with no
length limit, no sanitisation, and no check that it is a string. Combined with
API-1 (fallbacks are cached and replayed), model-authored text becomes a
permanent cached answer. The other tools all run through validated Pydantic
models; this one does not.

**Impact.** Titles can read `Top 5 HKWorkoutActivityTypeRunning`, and a model
that returns an object for `text` triggers an error that the router turns into a
generic 500. The replace also cannot be fixed once without fixing formatting for
every template, because each template gets a different mutation.

**Fix.** Drop the display rewriting from dispatch and let the template renderer
call `display_activity_type` (the frontend already has the shared formatting
helpers for this). Coerce and bound the fallback text (`str(...)`, strip, cap at
a few hundred characters) and run it through a Pydantic model like the other
args.

---

## LLM-8 — The benchmark harness records every run as if it were the result and never fails on its own threshold

**Low** — `backend/app/bench/runner.py:17-72`

`best_of` calls `run_benchmark` in a loop, so each of the N runs emits its own
`benchmark:<name>` diagnostics event carrying that run's duration and a status
computed from the threshold; only the fastest is returned, and nothing raises
when a run exceeds the threshold. The module docstring says the threshold exists
"so a material regression fails loudly", but the enforcement is entirely in the
caller's assertion on the returned value. `run_benchmark` also measures a single
wall-clock duration with no warmup and no repetitions, so a JIT/cache-cold first
call is what gets recorded.

**Impact.** The diagnostics stream shows one event per repetition where one
would do, with `over_threshold` on iterations that are then discarded — a
reported failure that is not one. The single-shot measurement makes the number
noisy in CI, which in turn makes a real regression hard to distinguish from
variance.

**Fix.** Record one event per `best_of` invocation (pass `run_benchmark`
`record=False` for inner runs, or aggregate), and have `best_of` raise (or
return a status the caller must check) when the best run still exceeds the
threshold.

---

## LLM-9 — The env-file loader mutates the process environment and drops inline comments; `get_model()` bypasses it

**Low** — `backend/app/llm/client.py:19-51`, `:64-96`, `:108-114`

`_load_env_file` writes every `KEY=VALUE` it finds into `os.environ`, once per
process (`_env_loaded`, no lock; harmless under the GIL but not self-evident).
Values are only quote-stripped, so `LLM_MODEL=gemma-3-27b # local default`
becomes the literal model name including the comment. `_ensure_env_loaded`
resolves the repo root as `Path(__file__).resolve().parents[3]`, which is
correct for a source checkout and wrong for any packaged install. The last
function in the file, `get_model()`, reads `LLM_MODEL` without calling
`_ensure_env_loaded`, so its result depends on whether some earlier call created
a client; it currently has no callers at all, which is the only reason the
inconsistency is invisible.

**Impact.** A `.env` written the way the repository's own example files suggest
(inline comments) produces a garbled model name and an opaque provider 404.
Nothing in the test suite exercises the loader.

**Fix.** Parse inline comments, keep the loader idempotent per path, make
`get_model()` a thin wrapper over the same path, and either delete it or use it
everywhere a model name is read.

---

## Cross-references

- The duplicate `get_data_profile` call in the request path is API-8, together
  with the planner prompt being built before the local plan is checked.
- The fallback and disambiguation responses written into the response cache are
  API-1 and API-2; LLM-7 is about the text they carry.
- The `_ensure_ready()` gaps in `finish_turn`/`terminate_turn` that the chat
  error paths rely on are API-7.
