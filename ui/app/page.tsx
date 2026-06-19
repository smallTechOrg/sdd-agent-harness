"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

type Dataset = { id: string; name: string };
type Column = { name: string; type: string };
type Table = { table_name: string; filename: string; n_rows: number; n_cols: number; columns: Column[] };
type ChartSpec = { data: unknown[]; layout: Record<string, unknown> };
type Msg = {
  role: "user" | "assistant";
  text: string;
  runId?: string;
  chartSpec?: ChartSpec;
};

async function getJSON(path: string) {
  const r = await fetch(`${API}${path}`);
  return r.json();
}

function tryParseChart(text: string): ChartSpec | undefined {
  // Look for a JSON object with "data" and "layout" keys embedded in the answer
  const match = text.match(/\{[\s\S]*"data"[\s\S]*"layout"[\s\S]*\}/);
  if (!match) return undefined;
  try {
    const spec = JSON.parse(match[0]) as ChartSpec;
    if (Array.isArray(spec.data) && spec.layout) return spec;
  } catch {
    // not valid JSON
  }
  return undefined;
}

export default function Home() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [tables, setTables] = useState<Table[]>([]);
  const [newName, setNewName] = useState("");
  const [goal, setGoal] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [threadId, setThreadId] = useState<string>(() => crypto.randomUUID());
  const [streaming, setStreaming] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadDatasets = useCallback(async () => {
    const j = await getJSON("/datasets");
    if (j.ok) {
      setDatasets(j.data);
      setSelected((cur) => cur || (j.data[0]?.id ?? ""));
    }
  }, []);

  const loadSchema = useCallback(async (id: string) => {
    if (!id) return setTables([]);
    const j = await getJSON(`/datasets/${id}`);
    if (j.ok) setTables(j.data.tables);
  }, []);

  useEffect(() => { loadDatasets(); }, [loadDatasets]);
  useEffect(() => { loadSchema(selected); }, [selected, loadSchema]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);

  async function createDataset() {
    if (!newName.trim()) return;
    const r = await fetch(`${API}/datasets`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    const j = await r.json();
    if (j.ok) {
      setNewName("");
      await loadDatasets();
      setSelected(j.data.id);
    }
  }

  async function uploadFile(file: File | undefined) {
    if (!file || !selected) return;
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${API}/datasets/${selected}/files`, { method: "POST", body: fd });
    const j = await r.json();
    if (!j.ok) setError(j.error ?? "upload failed");
    else await loadSchema(selected);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function ask() {
    const q = goal.trim();
    if (!q || busy) return;
    setBusy(true);
    setError("");
    setStreaming("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setGoal("");

    try {
      // SSE streaming
      const resp = await fetch(`${API}/runs/stream`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ goal: q, dataset_id: selected || null, thread_id: threadId }),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalAnswer = "";
      let finalRunId: string | undefined;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.token) {
              setStreaming((s) => s + ev.token);
            } else if (ev.done) {
              finalAnswer = ev.answer ?? "";
              finalRunId = ev.run_id;
              if (ev.thread_id) setThreadId(ev.thread_id);
            } else if (ev.error) {
              throw new Error(ev.error);
            }
          } catch {
            // non-JSON line, skip
          }
        }
      }

      // If streaming gave us no done event, fall back to the buffered streaming text
      if (!finalAnswer) finalAnswer = streaming;

      const chartSpec = tryParseChart(finalAnswer);
      const displayText = chartSpec
        ? finalAnswer.replace(/\{[\s\S]*"data"[\s\S]*"layout"[\s\S]*\}/, "").trim()
        : finalAnswer;

      setStreaming("");
      setMessages((m) => [
        ...m,
        { role: "assistant", text: displayText || finalAnswer, runId: finalRunId, chartSpec },
      ]);
    } catch (e) {
      // Fall back to non-streaming POST /runs
      try {
        const r = await fetch(`${API}/runs`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ goal: q, dataset_id: selected || null, thread_id: threadId }),
        });
        const j = await r.json();
        if (j.ok) {
          const answer = j.data.answer ?? "(no answer)";
          const chartSpec = tryParseChart(answer);
          const displayText = chartSpec
            ? answer.replace(/\{[\s\S]*"data"[\s\S]*"layout"[\s\S]*\}/, "").trim()
            : answer;
          if (j.data.thread_id) setThreadId(j.data.thread_id);
          setMessages((m) => [...m, {
            role: "assistant", text: displayText, runId: j.data.run_id, chartSpec,
          }]);
        } else {
          setError(j.error ?? "run failed");
          setMessages((m) => [...m, { role: "assistant", text: `Error: ${j.error}` }]);
        }
      } catch (e2) {
        setError(String(e2));
      }
      setStreaming("");
    } finally {
      setBusy(false);
    }
  }

  const lastAssistant = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i;
    return -1;
  })();

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">DataChat</h1>
        <p className="text-sm text-slate-500">
          Upload CSV/JSON datasets, then ask questions in plain English — answers grounded in
          read-only SQL, charts rendered inline.
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        {/* Upload / Dataset panel */}
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Datasets</h2>

          <label className="block text-xs text-slate-500 mb-1" htmlFor="dataset">Active dataset</label>
          <select
            id="dataset"
            aria-label="dataset"
            className="mb-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {datasets.length === 0 && <option value="">— none yet —</option>}
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>

          <div className="mb-3 flex gap-2">
            <input
              aria-label="new dataset name"
              placeholder="New dataset name"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") createDataset(); }}
            />
            <button
              onClick={createDataset}
              className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
            >
              Create
            </button>
          </div>

          <label className="block text-xs text-slate-500 mb-1">Upload CSV / JSON</label>
          <input
            ref={fileRef}
            type="file"
            aria-label="upload file"
            accept=".csv,.json,.ndjson,.jsonl"
            disabled={!selected}
            onChange={(e) => uploadFile(e.target.files?.[0])}
            className="mb-3 w-full text-sm file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-sm disabled:opacity-40"
          />

          {tables.length > 0 && (
            <>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Tables</h3>
              <ul className="space-y-2 text-sm">
                {tables.map((t) => (
                  <li key={t.table_name} className="rounded-md bg-slate-50 p-2">
                    <div className="font-medium">{t.table_name}
                      <span className="ml-1 text-slate-400">({t.n_rows} rows)</span>
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {t.columns.slice(0, 6).map((c) => `${c.name}: ${c.type}`).join(" · ")}
                      {t.columns.length > 6 && ` · +${t.columns.length - 6} more`}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="mt-4 border-t border-slate-100 pt-3">
            <p className="text-xs text-slate-400">
              Thread ID: <span className="font-mono">{threadId.slice(0, 8)}…</span>
              <button
                onClick={() => { setThreadId(crypto.randomUUID()); setMessages([]); }}
                className="ml-2 underline hover:text-slate-600"
              >
                new
              </button>
            </p>
          </div>
        </section>

        {/* Chat panel */}
        <section className="flex min-h-[520px] flex-col rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex-1 space-y-3 overflow-y-auto pr-1">
            {messages.length === 0 && !streaming && (
              <p className="text-sm text-slate-400">
                {datasets.length === 0
                  ? "Create a dataset and upload a CSV or JSON file to get started."
                  : "Ask a question about your data, e.g. "Which category has the highest total sales?""}
              </p>
            )}

            {messages.map((m, i) => (
              <div key={i}>
                <div
                  data-testid={m.role === "assistant" && i === lastAssistant ? "answer" : undefined}
                  className={
                    m.role === "user"
                      ? "ml-auto max-w-[80%] rounded-lg bg-slate-800 px-3 py-2 text-sm text-white"
                      : "mr-auto max-w-[95%] rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap"
                  }
                >
                  {m.text}
                  {m.role === "assistant" && m.runId && (
                    <div className="mt-1 text-xs">
                      <a
                        aria-label="trace"
                        href={`${API}/traces`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 underline"
                      >
                        View trace ↗
                      </a>
                    </div>
                  )}
                </div>

                {m.chartSpec && (
                  <div className="mr-auto mt-2 max-w-[95%] rounded-lg border border-slate-200 bg-white p-2">
                    <Plot
                      data={m.chartSpec.data as Plotly.Data[]}
                      layout={{ ...m.chartSpec.layout, autosize: true } as Partial<Plotly.Layout>}
                      style={{ width: "100%", height: 320 }}
                      config={{ responsive: true, displayModeBar: false }}
                    />
                  </div>
                )}
              </div>
            ))}

            {/* In-flight streaming token display */}
            {streaming && (
              <div className="mr-auto max-w-[95%] rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap">
                {streaming}
                <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-slate-500" />
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {error && (
            <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
          )}

          <div className="mt-3 flex items-end gap-2 border-t border-slate-100 pt-3">
            <textarea
              aria-label="goal"
              rows={2}
              placeholder={datasets.length === 0 ? "Upload a dataset first…" : "Ask a question about your data…"}
              disabled={datasets.length === 0}
              className="flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
              }}
            />
            <button
              onClick={ask}
              disabled={busy || datasets.length === 0}
              className="h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {busy ? "Asking…" : "Run"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
