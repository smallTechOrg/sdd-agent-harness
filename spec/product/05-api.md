# API

> **Boilerplate status:** Filled in by the tech-designer sub-agent. Delete this file if the agent has no external API surface (e.g., it's a pure CLI tool or background worker).

---

## API Style

<!-- FILL IN: default is an async FastAPI REST API + UI (the default trigger); REST / GraphQL / CLI /
     webhook / none. Errors return as JSON via the response envelope (ok / api_error), never an HTML
     error page — the Next.js frontend renders them. -->
<!-- Interaction model (multi-turn chat vs. single-shot task) is chosen at intake — state which here. -->

## Endpoints / Commands

<!-- FILL IN: One section per endpoint or command. -->

### `<!-- METHOD /path or command name -->`

**Purpose:** <!-- what this endpoint does -->

**Request:**
```json
{
  "<!-- field -->": "<!-- type and description -->"
}
```

**Response:**
```json
{
  "<!-- field -->": "<!-- type and description -->"
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | <!-- bad input --> |
| 500 | <!-- internal error --> |

## Authentication

<!-- FILL IN: How are API callers authenticated? -->
