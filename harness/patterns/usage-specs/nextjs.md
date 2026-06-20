# Usage-spec: Next.js (+ React)

**Version: `next` 15.x · `react` 19.x** (verify latest before pinning — a bump REFRESHES this file)
**Stamped: 2026-06 · App Router is the default; the Pages Router is legacy.**

Guards: `interface.md` § UI. The core ships the UI shell as **tested core** (Decision #1/#10); `/build`
configures the **primary-journey** page (one page: enter a goal → see the answer stream → link to its
trace). It does NOT rebuild `/traces` (the server renders that).

## App Router — the layout the core relies on
```
ui/app/layout.tsx        # root layout (App Router)
ui/app/page.tsx          # the primary-journey page — "use client" (it has state + fetch)
```
- ✅ **App Router** (`app/` dir), not the legacy **Pages Router** (`pages/` dir) — don't mix them.
- ✅ The interactive page is a **Client Component**: first line `"use client";` (it holds input/answer state
  and calls `fetch`). ❌ A Server Component can't use `useState`/`useEffect` or the browser `fetch`-stream —
  forgetting `"use client"` is the most common build error here.

## Calling the real agent (honesty — no mocks)
```tsx
"use client";
const res = await fetch("http://localhost:8001/runs", {
  method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({ goal }),
});
const { ok, data } = await res.json();      // the FastAPI envelope: { ok, data } | { ok:false, error }
```
- ✅ Read the `ok()` envelope shape (`data.answer`, `data.run_id`, + any structured field). ❌ No mocked
  answer, no fake latency, no lorem — a real call to the real agent (`localhost:8001`).
- For SSE, consume `/runs/stream` with `EventSource` / `fetchEventSource`; stream tokens into the markdown
  surface. The final `done` event carries `{answer, run_id, thread_id, ...}` — render `run_id` as the trace
  link.

## Render the answer as MARKDOWN (not raw text)
```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
<ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
```
- ✅ LLM output *is* markdown — render via `react-markdown` + `remark-gfm` (tables/strikethrough). ❌ Never
  `{answer}` in a `<pre>` or raw text; a wall of unformatted text is a bug.

## Deep-link the trace + persist the session
- ✅ Show `run_id` as a link to `http://localhost:8001/traces` (the server already renders the timeline —
  don't rebuild it).
- ✅ Multi-turn: store `thread_id` (and any active resource id) in `localStorage` so a reload resumes the
  same conversation — React state alone resets to a fresh thread on refresh ("my history vanished" bug).

## Dev/run gotchas
- ✅ Dev port **3001** (not 3000 — conflicts with Grafana/other local tools). The backend is **8001**.
- ✅ One command runs both: `make dev` → `trap 'kill 0' INT; python -m agent & cd ui && npm run dev` (Ctrl-C
  kills both). A UI with a dead backend is the #1 false "it's broken" report.
- ⚠️ A **browser-only library evaluated server-side** crashes SSR — disable SSR for that component
  (`dynamic(() => import(...), { ssr: false })`) rather than guessing. Read the dev-server log; the first
  error line names the cause.
- The browser-journey Playwright test asserts the **post-hydration DOM** (the answer + the visible trace
  link), never a raw-HTML 200 — that's the demo gate's UI half (`gates.md`).
