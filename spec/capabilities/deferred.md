# Deferred Capabilities (Phase 2–5 — labelled STUBS in Phase 1)

Brief stubs. Each is a clearly-labelled "coming soon" region in Phase 1 and is wired real in the noted phase. See `roadmap.md` for the per-phase slices and gates.

## Dataset Profile *(Phase 2)*
Full column profile on load — types, ranges, missing counts, cardinality, top values — computed in DuckDB. **Success:** profile values match DuckDB ground truth on the large fixture.

## Follow-up Suggestions *(Phase 2)*
`suggest_followups` node returns 2–3 next questions after each answer. **Success:** 2–3 relevant chips appear and asking one runs that question.

## Live Streaming Progress *(Phase 3)*
SSE endpoint streams stage events + answer chunks + cost as the run forms. **Success:** ordered stage/chunk/cost events on `GET /analyses/{id}/stream`.

## Daily Cost Rollup *(Phase 3)*
`cost_log` writes per run + `GET /cost/daily`. **Success:** daily total = sum of the day's run costs.

## Column Notes & Business Rules *(Phase 3)*
User notes/rules ("revenue excludes refunds") injected into `plan`/`generate_code`. **Success:** a rule provably changes the generated code/result.

## Export *(Phase 4)*
Export result CSV / chart PNG / run report. **Success:** valid CSV/PNG/report produced.

## Saved Derived Datasets *(Phase 4)*
Persist a derived result as a new DuckDB table reusable as a source. **Success:** a saved dataset is queryable in a new analysis.

## Analysis Library *(Phase 4)*
Revisit and re-run past analyses (view over `runs`). **Success:** re-running a library entry reproduces its result.

## Connected Database *(Phase 5)*
Attach a local DuckDB/SQLite file as a read-only source. **Success:** a connected source's tables are queryable.

## Multi-File Joins *(Phase 5)*
Upload multiple files; auto-infer relationships; answer across them. **Success:** two files with a shared key produce a correct joined answer; inferred join matches ground truth.
