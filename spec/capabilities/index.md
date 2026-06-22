# Capabilities Index

## Capabilities in This Project

| Capability | File | Summary |
|------------|------|---------|
| Dataset Upload | [dataset-upload.md](dataset-upload.md) | Accept CSV/JSON files, infer schema, register in session |
| NL Query | [nl-query.md](nl-query.md) | Translate a natural-language question to a validated SQL SELECT via Gemini |
| Query Execution | [query-execution.md](query-execution.md) | Execute validated SQL against stored datasets; write audit log entry |
| Session Management | [session-management.md](session-management.md) | Create and restore server-side sessions binding datasets and conversation history |

## Capability Dependencies

```
Session Management  ←  all other capabilities depend on an active session
        |
        ├── Dataset Upload        (writes dataset metadata to session)
        │
        └── NL Query              (reads schema from session)
                |
                └── Query Execution   (executes SQL; writes audit log)
```

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning
