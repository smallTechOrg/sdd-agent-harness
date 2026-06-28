# Capabilities Index

## Capabilities in This Project

| Capability | Phase | File |
|-----------|-------|------|
| Data Analysis | Phase 1 (CSV), Phase 2 (PostgreSQL), Phase 3 (Excel + multi-turn) | [data_analysis.md](data_analysis.md) |

## Capability Summary

**Data Analysis** — The core and only capability. Given a file or database connection, the agent translates a plain-English question into Pandas/SQL code, executes it locally, and returns a text answer plus an interactive Plotly chart specification. See [data_analysis.md](data_analysis.md) for the full spec.

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning
