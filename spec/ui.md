# UI

> Next.js 15 static export (`output: 'export'`, `basePath: '/app'`), React 19, Tailwind v4, served by FastAPI at `http://localhost:8001/app/`. Single page, single local user. Extends the skeleton's `frontend/src/app/page.tsx` (replaces the transform form). Inner-loop dev uses `pnpm dev`, but the canonical run + test path is `pnpm build` → `uv run python -m src` → `:8001/app/` (see `harness/patterns/tech-stack.md`). Every later-phase surface ships in Phase 1 as a clearly-labelled non-functional stub via a shared `StubCard` ("Coming in a later phase") so a stub is never mistaken for a bug.

---

## Layout (Phase 1)

```
┌──────────────────────────────────────────────────────────────┐
│ Library & History  [STUB]   │   Personal Data Analyst         │
│ ─────────────────────────── │   ┌──────────────────────────┐  │
│  (labelled stub sidebar:    │   │ UploadBar: [Upload CSV]   │  │
│   list of files, history)   │   │  orders.csv · 412k rows · │  │
│                             │   │  9 cols  [+ add file STUB]│  │
│                             │   └──────────────────────────┘  │
│                             │   ┌──────────────────────────┐  │
│                             │   │ QuestionBox  [Ask]        │  │
│                             │   └──────────────────────────┘  │
│                             │   ┌──────────────────────────┐  │
│                             │   │ AnswerPanel               │  │
│                             │   │  • live step updates      │  │
│                             │   │  • answer + key numbers   │  │
│                             │   │  • result table           │  │
│                             │   │  ▸ Plan (collapsible)     │  │
│                             │   │  ▸ Code (collapsible)     │  │
│                             │   │  Cost: 1.2k in / 0.4k out │  │
│                             │   │        ≈ $0.0003          │  │
│                             │   │  [Charts STUB] [Follow-   │  │
│                             │   │   ups STUB] [Daily $ STUB]│  │
│                             │   └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Components & Phase status

| Component | Phase 1 | Later |
|-----------|---------|-------|
| `UploadBar` | **Real** — upload CSV, shows filename, row/column counts | P4: multi-file add, library binding |
| `QuestionBox` | **Real** — text box + Ask button | — |
| `AnswerPanel` | **Real** — orchestrates the views below + live step updates while pending | — |
| `KeyNumbers` | **Real** — the headline numbers from the answer | — |
| `ResultTable` | **Real** — bounded result table | — |
| `PlanView` | **Real** — collapsible ordered plan | — |
| `CodeView` | **Real** — collapsible generated SQL/pandas per step | — |
| `CostChip` | **Real** — tokens in/out + estimated USD for this question | — |
| step-update stream | **Real** — renders `steps` as they persist (polled) | — |
| `cost_guard_warning` banner | **Real** — "Hit the step limit — best answer so far" when set | — |
| `ChartView` | **Stub (labelled)** | **P3 Real** — interactive (zoom/hover/filter) |
| `ProfilePanel` | **Stub (labelled)** | **P2 Real** — column types/ranges/nulls/quality |
| `FollowupChips` | **Stub (labelled)** | **P2 Real** — 2–3 clickable follow-ups |
| `LibrarySidebar` | **Stub (labelled)** | **P4 Real** — list/select/delete files |
| `HistoryBrowser` | **Stub (labelled)** | **P4 Real** — revisit past Q&A with plan/code/results |
| `DailyCostBadge` | **Stub (labelled)** | **P4 Real** — running daily total |
| `MultiFilePicker` | **Stub (labelled)** | **P4 Real** — add/compare/join files |
| conversation thread | **Stub (labelled)** | **P4 Real** — durable cross-day chat |

## Interactions (Phase 1)

1. **Upload:** click Upload CSV → file posts to `POST /datasets` → UploadBar shows filename + counts; QuestionBox enables.
2. **Ask:** type question → Ask → `POST /questions`; while `pending`, AnswerPanel polls `GET /questions/{id}` and renders live step updates ("Planning…", "Step 1: running SQL…").
3. **Answer:** on `completed`, render answer + key numbers + result table, with collapsible Plan and Code and the Cost chip. If `cost_guard_warning` is set, show the warning banner above the answer.
4. **Failure:** on `failed`, AnswerPanel shows the error and the steps it did run (what it tried, where it got stuck) — never a blank screen.

## Accessibility / polish notes

- Collapsibles are keyboard-operable; code blocks are monospaced with copy.
- Stubs use the shared `StubCard` with a muted style + a clear "Coming in a later phase" pill so they read as roadmap, not breakage.

## E2E (Playwright — required gate)

`frontend/tests/e2e/phase1.spec.ts` drives the real app at `:8001/app/`: upload a fixture CSV, ask a question, assert the answer text, a result-table cell, the Plan/Code collapsibles, and the Cost chip all render with real output (not a spinner/error). A 200-only or CSS-only check is not sufficient. Later phases add `phase2/3/4.spec.ts`.
