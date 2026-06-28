# Capability: Multi-File Analysis

## What It Does
Lets the user ask questions that span multiple files: the agent picks the right file(s) for the question and can join or compare across files on a shared key — all computed locally. (Phase 4)

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| question text | str | `POST /questions` | yes |
| library schemas + sample rows | JSON | all `datasets` rows | yes |
| selected files (optional) | list | UI MultiFilePicker | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chosen dataset_ids | rows | `question_datasets` |
| joined/compared result | JSON (bounded) | `questions` result table; UI |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini Flash | rank/select files + generate cross-file SQL (schemas + sample rows only) | surfaced error; falls back to single-file |
| DuckDB (local) | join/compare across CSVs on a shared key over full data | step error → replan/surface |

## Business Rules
- The LLM sees only schemas + sample rows of candidate files to choose and write the join — never full rows from any file.
- The join executes locally in DuckDB across the full datasets.
- The agent flags its file choice and any assumptions (best-guess + assumptions per the uncertainty rule).

## Success Criteria
- [ ] A question spanning two files on a shared key returns a correct joined result computed over full data.
- [ ] The agent selects the correct file(s) without the user naming them, and shows which it chose.
- [ ] A side-by-side comparison across two files returns correct per-file figures.
