# Capabilities Index

## Capabilities in This Project

| # | Capability | File |
|---|-----------|------|
| 1 | Connect a CSV file as a data source (wraps its Parquet in an MCP server) | [01-connect-csv.md](01-connect-csv.md) |
| 2 | Answer natural language questions via an iterative MCP tool-call ReAct loop | [02-nl-query-iterative.md](02-nl-query-iterative.md) |
| 3 | Manage sessions per data source (create, list, delete) | [03-sessions.md](03-sessions.md) |

## Future Capabilities (deferred)

| # | Capability | Target Phase |
|---|------------|--------------|
| 4 | Non-CSV data source types: REST API, GraphQL, shell | Phase 4 |
| 5 | Charts & Visualizations | Phase 5 |
| 6 | AI-written Insights | Phase 6 |
| 7 | React/Vite Frontend | Phase 5 |
| 8 | Multi-user / authentication | Phase 7 |

## How to Add a New Capability

Run `/spec-new-capability [description]` or ask the spec-writer directly. The spec-writer will:
1. Create a new file in this directory
2. Update this index
3. Flag any dependencies on existing capabilities
4. The spec-reviewer will validate it fits the architecture
