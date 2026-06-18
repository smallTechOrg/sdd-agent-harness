# API

## API Style

REST (JSON). All routes return `{"data": ..., "error": null}` on success or raise an HTTP 4xx/5xx with `{"detail": {"code": "...", "message": "..."}}` on error.

## Endpoints

### GET /health

Returns server status and current LLM provider.

**Response 200:**
```json
{
  "data": {
    "status": "ok",
    "llm_provider": "gemini"   // or "stub"
  },
  "error": null
}
```

### POST /api/sessions

Upload a CSV or JSON file. Creates a session and parses the data into an in-memory DataFrame.

**Request:** `multipart/form-data` with field `file` (CSV or JSON).

**Response 200:**
```json
{
  "data": {
    "session_id": "uuid",
    "filename": "sales.csv",
    "status": "ready",
    "row_count": 1234,
    "column_names": ["region", "amount", "date"]
  },
  "error": null
}
```

**Errors:** 400 if file type not supported; 413 if file exceeds max size; 422 if parse fails.

### GET /api/sessions/{session_id}

Get session metadata.

**Response 200:**
```json
{
  "data": {
    "session_id": "uuid",
    "filename": "sales.csv",
    "status": "ready",
    "row_count": 1234,
    "column_names": ["region", "amount", "date"],
    "created_at": "2026-06-18T12:00:00Z"
  },
  "error": null
}
```

### POST /api/sessions/{session_id}/messages

Ask a plain-English question about the uploaded dataset. Runs the ReAct agent synchronously and returns the answer.

**Request:**
```json
{ "question": "What is the average amount by region?" }
```

**Response 200:**
```json
{
  "data": {
    "answer": "The average amount by region is: North $1,200, South $980...",
    "reasoning_trace": [
      {"action": "df.groupby('region')['amount'].mean()", "result": "North    1200.0\nSouth     980.0", "is_error": false}
    ],
    "llm_provider": "gemini"
  },
  "error": null
}
```

### GET /api/sessions/{session_id}/messages

Return the full message history for a session.

**Response 200:**
```json
{
  "data": [
    {"id": "uuid", "role": "user", "content": "What is the average amount?", "created_at": "..."},
    {"id": "uuid", "role": "assistant", "content": "The average is $1,090.", "reasoning_trace": [...], "created_at": "..."}
  ],
  "error": null
}
```
