# Capability: Persistent Dataset Browser

## What It Does

Lets the user browse every dataset they have uploaded across sessions, switch to a past dataset (re-loading its profile and making it the active dataset for new questions), and re-open any of its prior question runs — answer, chart, table, and show-its-work — reconstructed from the persisted record with no new LLM call.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| (list datasets) | — | `GET /datasets` (no params) | yes |
| dataset_id | string (uuid) | sidebar selection → `GET /datasets/{id}` (profile) + `GET /datasets/{id}/runs` (history) | yes |
| run selection | run_id | a click on a past question in the history list (renders from the already-fetched run record) | no |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Dataset summaries | array of `{id, name, row_count, status, question_count, created_at}` (newest first) | sidebar list |
| Active dataset profile | the existing `Dataset` profile shape | profile card (re-rendered) |
| Run history | array of `RunRecord` (the live `AskResult` shape + `question` + `created_at`, newest first) | run-history list + re-opened answer panel |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (app DB) | read `datasets` + `COUNT(question_runs)` for the list; read `question_runs` for history | inline error ("Couldn't load your datasets — is the server running?") |
| LLM | **none** — the browser never calls the LLM | n/a (re-opening history is free and private) |

## Business Rules

- **No new schema / migration** — reads the Phase-1 `datasets` + `question_runs` tables only.
- **Newest first** — both the dataset list and the per-dataset run history order by `created_at` descending.
- **Re-open ≠ re-ask** — re-opening a past run reconstructs the answer/chart/table from the persisted `result_json`/`chart_json` (via the same `_ask_payload`/`_chart_data` logic as a live ask), making **no LLM call** and sending **no raw rows** anywhere. It renders identically to when first answered.
- **Same render path** — a `RunRecord` is the `AskResult` shape (plus `question`/`created_at`), so the existing `AnswerPanel`/`Chart`/`SummaryTable`/`ShowItsWork` render it with no new component.
- **Switching sets the active dataset** — new questions target the selected dataset.
- **Empty vs error vs 404** — an existing dataset with no runs returns `200` + `[]` (empty state, not red); a missing dataset returns `404 NOT_FOUND`; a fetch failure shows a red inline error distinct from both.

## Success Criteria

- [ ] `GET /datasets` lists every uploaded dataset newest-first, each with a correct `question_count`; empty case returns `[]`.
- [ ] Selecting a past dataset re-loads its profile (via existing `GET /datasets/{id}`) and shows its run history.
- [ ] `GET /datasets/{id}/runs` returns each run in the `AskResult` shape with `chart.data` and `table` reconstructed identically to the live ask, plus `question` and `created_at`.
- [ ] Re-opening a past run renders the same answer + chart + table + show-its-work as the original, and makes **no LLM call** (verifiable: history fetch logs no LLM input).
- [ ] `GET /datasets/{missing}/runs` returns `404`; an existing dataset with zero runs returns `200` + `[]`.
- [ ] Switching datasets sets the active dataset, and a new question on it appends to the top of the history.
