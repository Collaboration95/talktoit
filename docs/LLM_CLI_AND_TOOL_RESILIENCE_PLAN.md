# LLM CLI and Tool-Call Resilience Plan

## Background

The current chat path can fall back to "No answer available" even when the
backend query logic is correct. A recent failure showed the root cause:

- the model produced a malformed tool name with a leading tab
- the OpenAI-compatible API rejected the tool call before the backend
  dispatcher could run
- the frontend only saw the fallback response, so the user lost the answer

This is a transport/problem-shaping issue, not a query bug.

## Goals

1. Prevent malformed model tool output from breaking the request flow.
2. Add a headless CLI that reuses the same backend orchestrator.
3. Make the CLI useful for both humans and automation:
   - one-shot question execution
   - optional JSON output for scripting
   - interactive prompt fallback when no question is passed
4. Keep the browser app and CLI on the same backend logic path.

## Non-goals

- Rebuilding the frontend.
- Adding a second query engine.
- Changing the persisted data model.

## Proposed Changes

### 1. Replace server-side tool calls with local tool planning

The current orchestrator asks the model to emit a tool call directly through
the OpenAI tool-calling API. That is where the 400 happens when the model
produces a malformed tool name.

The fix is to split the flow into two plain chat-completion steps:

1. Ask the model to return a small JSON object describing the tool choice.
2. Validate and normalize that JSON locally before dispatching the tool.
3. Generate the narrative from the tool result.

This removes the server-side tool-call validation failure entirely.

```python
plan = await model_plan(question)
tool_name = plan["tool_name"].strip()
template_id, data = dispatch_tool(tool_name, plan["arguments"], conn, question)
```

### 2. Normalize tool names in the dispatcher

Add local normalization so benign whitespace differences do not break
dispatch. This is a second safety net, not the primary fix.

```python
tool_name = tool_name.strip()
```

### 3. Add a backend CLI entrypoint

Create a backend module that:

- loads the same `.env` configuration as the web app
- opens the same DuckDB database
- reuses `ChatOrchestrator`
- prints either a human-readable answer or JSON

Target usage:

```bash
make run-cli
make run-cli QUESTION="Which gym session had the highest heart rate last month?"
make run-cli QUESTION="..." JSON=1
```

### 4. Add a Makefile target

Expose the CLI through `make run-cli` so it becomes the primary headless
developer and automation entrypoint.

```make
run-cli:
\tuv run --directory backend python -m app.cli.chat
```

### 5. Add tests

Add regression coverage for:

- malformed tool names that should now be normalized locally
- CLI question execution and JSON formatting
- fallback behavior when the planner output is invalid JSON or the tool is
  unknown

## Files to Change

- `backend/app/llm/orchestrator.py`
- `backend/app/llm/tools.py`
- `backend/app/cli/__init__.py`
- `backend/app/cli/chat.py`
- `backend/tests/integration/test_chat.py`
- `backend/tests/unit/test_tools.py`
- `backend/tests/unit/test_cli_chat.py`
- `Makefile`
- `README.md`

## Acceptance Criteria

1. The question that previously failed with the tab-prefixed tool name now
   returns a valid answer instead of falling back.
2. No OpenAI-compatible 400 is triggered by malformed tool names.
3. `make run-cli` works without the browser.
4. `make run-cli QUESTION="..." JSON=1` prints machine-readable output.
5. Existing web/API behavior remains intact.
6. Tests cover the regression and the new CLI surface.

## Edge Cases

- Planner returns invalid JSON.
- Planner returns an unknown tool name.
- Planner returns an empty arguments object.
- The database is missing or the path is invalid.
- The CLI is run without `QUESTION` and without a TTY.

## Verification Strategy

1. Run backend unit and integration tests.
2. Run the new CLI test(s).
3. Run a manual `make run-cli QUESTION="..."` check against the local DB.
4. Run the existing app smoke path if needed to confirm no regression.
