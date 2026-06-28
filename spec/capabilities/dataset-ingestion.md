# Capability: Dataset Ingestion

## What It Does
Accepts an uploaded spreadsheet, persists the raw file to local disk, and auto-profiles it
(columns, dtypes, ranges, missing values, ≤5-row sample) so the agent has privacy-safe context.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | multipart upload (CSV in P1; XLSX in P4) | `POST /datasets` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| dataset record | row | `datasets` table |
| raw file | file | `uploads/<dataset_id>/<filename>` |
| profile | JSON (schema, stats, ≤5-row sample) | `datasets.profile_json` + API response + UI card |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local disk | Write uploaded file | Return `PROFILE_FAILED`/`BAD_UPLOAD`; no DB row |
| pandas | Load file + compute profile | Return `BAD_UPLOAD` (unparseable) |

## Business Rules
- Profile carries only aggregates + a sample capped at `MAX_SAMPLE_ROWS = 5` rows — this is the
  only row-level data the system will ever expose to the LLM (privacy invariant).
- Profiling runs off the request thread; a ~100MB file must not block the event loop.
- P1 supports a single CSV file; Excel/multi-sheet is P4.

## Success Criteria
- [ ] Uploading a valid CSV returns a profile with correct column names, dtypes, row count,
      numeric ranges, and missing-value counts.
- [ ] The persisted file exists under `uploads/` and a `datasets` row references it.
- [ ] `profile.sample` contains ≤5 rows.
- [ ] An unparseable upload returns `BAD_UPLOAD` and creates no `datasets` row.
