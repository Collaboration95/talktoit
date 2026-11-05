# Local chat from the terminal

Run these commands from the repository root. Python 3.12+ and `uv` are required.
Only backend dependencies are needed; no frontend build or HTTP server is needed.

```bash
uv sync --directory backend --dev --locked

# Skip this if your export is already imported. Use an absolute export path.
make ingest EXPORT_PATH=/absolute/path/to/export.xml

# Continuous chat with the local provider, even if Settings selects a remote one.
make run-cli INTERACTIVE=1 LOCAL=1
```

Ask a complete question, for example `Show my last run` or `Show running volume
this week`. After a period summary, try `Compare that to prior period`.
Use `/quit`, `/exit`, Ctrl-D or Ctrl-C to leave. Relative dates use the dataset's
latest date through the shared `ChatOrchestrator`, as they do in HTTP chat.

With a managed import, the loop saves questions and answers in local conversation
history and uses the previous turn for supported deterministic follow-ups. This
is not general conversational memory. Changing the active import resets the
conversation context. Explicit external or legacy databases without an active
manifest answer independently, without shared history or cache association.

## Local model selection

Recognized questions run through deterministic local planning and queries. They
can return answers without a running model. Open-ended wording needs a working
local provider; unavailable models return guidance through the existing fallback.

The CLI uses the installed runtime and the provider's saved endpoint/model.
To select an **already installed and served** model for this process:

```bash
make run-cli INTERACTIVE=1 LOCAL_MODEL=your-installed-model-id
# Equivalent backend invocation (uv changes cwd to backend):
uv run --directory backend python -m app.cli.chat --interactive --local-model your-installed-model-id
```

`--local-model` implies `--local`. Neither option changes saved Settings. There is
no model download or dependency installation in the CLI. The existing LiteRT
lifecycle may start an installed server. Set `TTI_LOCAL_AUTOSTART=0` to prevent
autostart, for example when using an already running server.

On first setup, `LITERT_MODEL` and `LITERT_BASE_URL` supply defaults. Saved Settings
take precedence over those environment defaults. `--local-model` overrides the
saved model; the endpoint still comes from the local provider settings and must
be a loopback URL. The configured runtime must actually serve that model.

Without `LOCAL=1`, `LOCAL_MODEL=...` or `--local`, the CLI follows saved provider
settings, including an explicitly configured remote provider. Use the local
options above for a local chat session.

## One question and automation

```bash
make run-cli LOCAL=1 QUESTION="Show my last run"
make run-cli LOCAL=1 QUESTION="Show my last run" JSON=1

# One compact ChatResponse envelope per input line; prompts/hints go to stderr.
printf '%s\n' 'Show running volume this week' 'Compare that to prior period' |
  make run-cli INTERACTIVE=1 LOCAL=1 JSON=1

# One-shot piped input is a single question, including any embedded newlines.
printf '%s\n' 'Show my last run' |
  uv run --directory backend python -m app.cli.chat --local --json
```

Human output keeps the question and narrative visible without dumping the data
payload. `--json` preserves the complete `ChatResponse` envelope; one-shot JSON
is indented, while interactive JSON is newline-delimited. Treat answers, JSON
and redirected output as private health data and keep them local.

For an explicit database, `make run-cli DB_PATH=...` resolves relative paths from
the repository root (including paths with spaces). With direct `uv --directory
backend` commands, use an absolute `--db-path`. The configured managed dataset
remains the default. `--cache-mode fresh` bypasses cached answers on the direct
CLI. Existing `--conversation-id` and `--parent-turn-id` can resume a known local
conversation; a parent ID requires its conversation ID.

Exit codes: `0` means a response was returned (including a useful fallback), or
the loop ended at EOF or `/quit`; `1` means startup or answering failed; `2`
means invalid arguments or one-shot input; `130` means Ctrl-C. Blank loop lines
are ignored. Oversized loop questions receive a stderr hint and the loop
continues. A runtime failure ends the process with code `1`; successful earlier
JSON lines remain valid. Questions must contain 1–2,000 characters.

If setup fails, check that backend dependencies are installed, an import is
active, and the configured local endpoint serves the selected model. The CLI
prints safe guidance instead of exception details containing paths or SQL.
If the dataset is busy, wait for the import to finish and retry.

## Next milestones and known gaps

1. Normalize energy units before relying on energy rankings or totals. Mixed source
   units remain unresolved; deterministic execution alone does not prove numeric correctness.
2. Build an independent numeric oracle over synthetic fixtures for date boundaries,
   aggregation, unit conversion and missing values; avoid sharing query implementation logic.
3. Freeze a versioned question corpus with expected scopes, tools, values and useful
   refusals. Evaluate each planner change against it and retain regressions; use a held-out
   set to keep iterative improvements from overfitting the corpus.
4. Qualify an installed local model separately: record runtime/model versions, actual
   planning and narration outcomes, latency and offline failures. Deterministic answers
   and stubbed tests do not establish running-model quality or readiness.

Cache v9 and persisted planner contract v4 exclude earlier scoped answers from
exact/canonical and semantic reuse without clearing local history or databases.
Current equivalent intents still share answers. The checks described here establish
synthetic software behavior, with no clinical conclusions.

## Actual local-runtime smoke: 5 November 2026

LiteRT-LM **0.15.0**, serving the already installed **gemma4-e2b**, passed a
synthetic generation and fixture-backed CLI smoke. This is one local model smoke,
not a general planner-quality evaluation. No dependencies or weights were downloaded.

First check for an existing listener; start only if the port is unused:

```bash
lsof -nP -iTCP:9379 -sTCP:LISTEN
"$HOME/litert-lm/.venv/bin/litert-lm" serve --host 127.0.0.1 --port 9379
```

The audit used the repository's `app.llm.litert.start` with explicit model/base URL,
a disposable `TTI_APP_STATE_PATH`, a 25-second startup deadline, and the exact serve
command above. Listener/model readiness took **0.559 seconds**; that alone did not
prove inference. A separate completion did:

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 120 \
  http://127.0.0.1:9379/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma4-e2b","messages":[{"role":"user","content":"Reply with READY only."}],"max_tokens":32,"temperature":0}'
```

The measured Python HTTP probe returned HTTP 200 and exactly **READY** in
**2.492 seconds**, with two completion tokens. The curl command is an equivalent
bounded manual probe.

For chat, `ingest_v2(..., n_workers=1)` ingested committed `tests/fixtures/sample.xml`
into disposable DuckDB and published a managed fixture generation with disposable
SQLite app state. It contained **40 records and 3 workouts**, with coverage
**1–10 June 2026**. Before creating clients, the audit bootstrap set
`app.llm.client._env_loaded = True` to prevent reading either `.env` file.
Process-only configuration selected `local`, `local_only`, `gemma4-e2b`, and
`http://127.0.0.1:9379/v1`, disabled autostart after the owned server was ready,
and disabled provider retries. The first run allowed 45 seconds per provider stage.
No production database, export, app state, or saved provider choice was used.

The actual interactive `app.cli.chat.main` path ran five inputs with fresh cache
mode. Observers called the original gateway and tool dispatch; they did not supply
plans, model responses, or query results. All five outputs validated as
`ChatResponse`, and fixture values were checked against explicit expected constants.

| Input | Actual result |
| --- | --- |
| `Could you retrieve whichever exercise session was logged most recently?` | Deterministic planner returned no plan. Gemma returned `get_last_workout` with `{}` arguments; normal validation and DuckDB execution returned `workout_card`: Cycling, `2026-06-08T18:00:00+08:00`, 120 minutes, 45,000 meters, average HR 138. |
| `Show my last run` | Deterministic `workout_card`: Running, 5 June, 45.5 minutes, 8,500 meters. Zero model calls. |
| `Show running volume this week` | Deterministic summary for 8–10 June, zero running sessions. Zero model calls. |
| `Compare that to prior period` | Deterministic comparison retained Running and compared 8–10 June against 5–7 June: zero versus one session; previous duration 45.5 minutes and distance 8.5 km. Zero model calls. |
| `Please prescribe medication for my headache.` | Gemma selected `get_fallback_answer`; application returned `fallback` / `clarification_needed`, discarded model fallback prose, and performed no tool query or narration. |

Held-out planning took **6.775 seconds**, real DuckDB tool dispatch **5.305 seconds**,
and separate model narration **2.757 seconds**. The narration correctly stated the
cycling date, duration, and 45 km distance. Unsupported-request planning took
**10.896 seconds**. The complete five-input loop exited 0 in **73.801 seconds**;
these stage timings do not include all CLI, snapshot, and state-store overhead.
Other observed tool dispatches also took about 5.3 seconds, so this smoke establishes
correctness but does not establish a responsive latency target.

A second run cleared only the disposable fixture cache and exercised the actual
Makefile entry point, with the same isolated database/state and dotenv-disabled
bootstrap inherited by the subprocess:

```bash
UV_NO_SYNC=1 UV_OFFLINE=1 make run-cli INTERACTIVE=1 LOCAL=1 LOCAL_MODEL=gemma4-e2b JSON=1
```

With the default **15-second per-stage provider deadline** and no retries, the
same held-out question returned the expected `workout_card`, actual model
narration, and `remote_planned` provenance; `/quit` exited 0. End-to-end wall time
was **28.897 seconds**, with empty stderr. This rules out dependence on the
first run's longer provider deadline for that question; it does not establish
that every wording will finish within 15 seconds.

The established envelope calls model planning `remote_planned` even when the
selected provider is loopback-local. Evidence here distinguishes local model
planning/narration from deterministic execution; no hosted model was called.
Presentation gaps observed in this smoke: the empty weekly summary narrative
printed `None km` / `None min` and used the title `June 2026`; the unsupported
request received generic clarification guidance. A subsequent synthetic regression
fix makes empty summaries say no workouts were recorded, labels missing totals
`unavailable`, and preserves measured zero with its unit. Persisted planner contract
v4 excludes the earlier wording from exact/canonical and semantic reuse without
deleting history. The title and unsupported-request guidance remain unchanged.
This wording fix was validated without additional model calls.

The focused provider, redaction, lifecycle and PID-ownership tests passed:
**46 tests in 4.66 seconds** (`pytest -o addopts= --no-cov -q` with the four
`test_provider_gateway.py`, `test_provider_redaction.py`, `test_litert_lifecycle.py`
and `test_litert_ownership.py` unit modules). This was targeted validation, not
a full-suite run or coverage-gate result. No runtime/provider code fix was needed.

The audit server was shut down after verification, and its process was confirmed
absent. The results above describe the completed synthetic smoke; they do not
indicate a currently running server. Use the launch instructions above when
another local-model session is needed.
