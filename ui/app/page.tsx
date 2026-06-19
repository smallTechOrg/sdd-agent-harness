"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

type Dataset = { id: string; name: string };
type Column = { name: string; type: string };
type Table = { table_name: string; filename: string; n_rows: number; n_cols: number; columns: Column[] };
type Msg = { role: "user" | "assistant"; text: string; runId?: string };

async function getJSON(path: string) {
  const r = await fetch(`${API}${path}`);
  return r.json();
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
  const fileRef = useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);
  useEffect(() => {
    loadSchema(selected);
  }, [selected, loadSchema]);

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
    setMessages((m) => [...m, { role: "user", text: q }]);
    setGoal("");
    try {
      const r = await fetch(`${API}/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ goal: q, dataset_id: selected || null }),
      });
      const j = await r.json();
      if (j.ok) {
        setMessages((m) => [...m, { role: "assistant", text: j.data.answer ?? "(no answer)", runId: j.data.run_id }]);
      } else {
        setError(j.error ?? "run failed");
        setMessages((m) => [...m, { role: "assistant", text: `Error: ${j.error}` }]);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const lastAssistant = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "assistant") return i;
    return -1;
  })();

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">DataChat</h1>
        <p className="text-sm text-slate-500">
          Upload CSV/JSON into a dataset, then ask questions in plain English. Answers are grounded in
          read-only SQL over your data — every run is traced.
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-[300px_1fr]">
        {/* Dataset panel */}
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Dataset</h2>

          <label className="block text-xs text-slate-500" htmlFor="dataset">Active dataset</label>
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
            />
            <button onClick={createDataset} className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700">
              Create
            </button>
          </div>

          <label className="block text-xs text-slate-500">Upload CSV / JSON</label>
          <input
            ref={fileRef}
            type="file"
            aria-label="upload file"
            accept=".csv,.json,.ndjson,.jsonl"
            disabled={!selected}
            onChange={(e) => uploadFile(e.target.files?.[0])}
            className="mb-3 w-full text-sm file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-sm"
          />

          <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Tables</h3>
          {tables.length === 0 ? (
            <p className="text-sm text-slate-400">No tables yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {tables.map((t) => (
                <li key={t.table_name}>
                  <div className="font-medium">{t.table_name} <span className="text-slate-400">({t.n_rows} rows)</span></div>
                  <div className="text-xs text-slate-500">{t.columns.map((c) => `${c.name}:${c.type}`).join(", ")}</div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Chat panel */}
        <section className="flex min-h-[420px] flex-col rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex-1 space-y-3 overflow-y-auto">
            {messages.length === 0 && (
              <p className="text-sm text-slate-400">
                Ask a question about your data, e.g. “Which category has the highest total sales?”
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                data-testid={m.role === "assistant" && i === lastAssistant ? "answer" : undefined}
                className={
                  m.role === "user"
                    ? "ml-auto max-w-[80%] rounded-lg bg-slate-800 px-3 py-2 text-sm text-white"
                    : "mr-auto max-w-[85%] rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap"
                }
              >
                {m.text}
                {m.role === "assistant" && m.runId && (
                  <div className="mt-1 text-xs">
                    <a aria-label="trace" href={`${API}/traces`} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                      View trace ↗
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>

          {error && <div className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

          <div className="mt-3 flex items-end gap-2">
            <textarea
              aria-label="goal"
              rows={2}
              placeholder="Ask a question about your data…"
              className="flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask();
                }
              }}
            />
            <button
              onClick={ask}
              disabled={busy}
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
