# Data Model

---

## Storage Technology

SQLite (local file, `sqlite:///./data/agent.db`) via SQLAlchemy 2.0 (`DeclarativeBase`), migrations by Alembic. SQLite is chosen because this is a single-user local tool — no shared/production database is needed, and keeping the DB local reinforces the "data stays local" constraint. The **uploaded CSV is not stored as a dataset** beyond the in-request DataFrame; only the run record (question, generated code, computed result, answer) is persisted.

## Entities

### Entity: Run

One analysis: a question asked of an uploaded CSV, plus everything needed to audit the answer. Extends the skeleton `RunRow` (table `runs`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (UUID) | yes | Primary key |
| status | Text | yes | `pending` → `completed` / `failed` |
| mode | Text | no | `"pandas"` or `"sql"` (Phase 2+); defaults to `"pandas"` for Phase 1 runs |
| input_text | Text | no | Legacy/back-compat: stores the question (the analyst path uses `question`); kept so existing skeleton code still works |
| question | Text | no | The natural-language question the user asked |
| generated_code | Text | no | The exact code that was executed (the "show its work" artifact): pandas snippet (Phase 1–2) or SQL query (Phase 2+) or both depending on mode |
| result_table | Text (JSON) | no | The computed result serialized as JSON: `{"columns": [...], "rows": [[...]]}` or a scalar wrapper |
| output_text | Text | no | Compact answer + explanation summary (back-compat with the skeleton response field) |
| answer | Text | no | The short answer line |
| explanation | Text | no | The plain-English explanation |
| error_message | Text | no | Set when `status = failed`; the categorized failure reason |
| created_at | TIMESTAMP(tz) | yes | Row creation time |
| updated_at | TIMESTAMP(tz) | yes | Last update time (on completion) |

> The uploaded **CSV text itself is intentionally NOT persisted** as a column — it is held only in memory for the duration of the request, consistent with the local-data constraint. (If a future phase wants reproducibility, persisting it locally is a deliberate, separate decision.)

### Relationships

None — a single flat `runs` table. (No multi-file, no joins, no users.)

## Data Lifecycle

- **Create:** a `Run` row is created (`pending`) when `POST /runs` is received.
- **Update:** the row is updated to `completed` (with answer/explanation/code/result) or `failed` (with `error_message`) when the graph finishes.
- **Read:** `GET /runs/{id}` returns the stored run.
- **Delete:** none automatic in v1 (single local user; manual DB file deletion if desired). No archival/time-boxing.

## Sensitive Data

- The **uploaded dataset** may contain PII/confidential data. It is processed **locally** and never sent to the LLM in full — only the schema + a capped sample + the question leave the machine (constraint 1). The full CSV is not persisted to the DB.
- The **capped sample** that goes to Gemini may contain a few real rows; this is the documented, accepted minimal context. Users should be aware the sample (≤20 rows) is transmitted. (A future phase could add sample redaction/synthesis.)
- `AGENT_GEMINI_API_KEY` is a secret, loaded from `.env` (gitignored), never logged or echoed.
