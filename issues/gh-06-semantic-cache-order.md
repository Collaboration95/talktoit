# GH-6 — `semantic_turns()` loads all responses per request; exact-cache lookup after heavy profile work (medium)

## Labels
`performance`, `priority: medium`

## Summary
Two related inefficiencies in the chat path:
- `AppStateRepository.semantic_turns(dataset)` selects `response_json` and the
  full canonical plan for **every** completed turn in the dataset and materializes
  them all in memory on each chat request (when semantic candidates are enabled),
  even though the matcher only needs the normalized question + canonical plan of
  all turns and the full response of at most one identical turn.
- The exact-cache lookup happens only **after** `get_data_profile(conn)` and
  `plan_local_question(question, profile)` have run, so a pure cache hit still
  pays a full profile scan (see GH-1).

## Locations
- `backend/app/state/app_state.py` (`get_semantic_turns` usage in `api/chat.py::_semantic_cached_answer`)
- `backend/app/api/chat.py`

## Proposed direction (no code)
- Trim `semantic_turns` to return only the columns the verifier needs
  (`id`, `normalized_question`, `canonical_plan_json`, and `response_json` only
  for a narrowed candidate set), and lazily fetch the identical turn's response.
- Reorder: resolve the cache key and check the exact cache **before** computing the
  data profile / local plan, so hits skip the scan.

## Acceptance
- A cache-hit request does not run a full profile scan; semantic matching no longer
  loads the full history into memory.
