"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API = "/api";

// ── helpers ────────────────────────────────────────────────────────────────

function genId() {
  // Prefer crypto.randomUUID for a collision-free per-tab id (gotcha C-SESSION-SCOPE);
  // fall back to Math.random for non-secure / older contexts.
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch {}
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// Safe localStorage that never throws — window.localStorage guards against
// SSR environments where Node 22 provides a non-functional localStorage global.
const ls = {
  get: (key) => { try { return window.localStorage.getItem(key); } catch { return null; } },
  set: (key, val) => { try { window.localStorage.setItem(key, val); } catch {} },
  remove: (key) => { try { window.localStorage.removeItem(key); } catch {} },
};

function getOrCreate(key, factory) {
  const v = ls.get(key);
  if (v) return v;
  const n = factory();
  ls.set(key, n);
  return n;
}

// ── Plotly chart component ─────────────────────────────────────────────────

function PlotlyChart({ spec }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !spec) return;
    const { data, layout } = spec;
    if (typeof window !== "undefined" && window.Plotly) {
      window.Plotly.newPlot(ref.current, data, { ...layout, responsive: true });
    }
  }, [spec]);
  return <div ref={ref} className="w-full mt-2" style={{ minHeight: 320 }} />;
}

// ── UploadPanel ────────────────────────────────────────────────────────────

function UploadPanel({ onUploaded }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const handleFile = useCallback(async (file) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("name", file.name.replace(/\.[^.]+$/, ""));
    try {
      const res = await fetch(`${API}/datasets/upload`, { method: "POST", body: form });
      const body = await res.json();
      if (!body.ok) throw new Error(body.error || "Upload failed");
      onUploaded(body.data);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  const onDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors
        ${dragging ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-blue-300"}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.json"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      {uploading ? (
        <p className="text-blue-600 font-medium">Uploading…</p>
      ) : (
        <>
          <p className="text-gray-500 text-sm">
            Drop a <strong>CSV</strong> or <strong>JSON</strong> file here, or click to browse
          </p>
          {error && <p className="text-red-500 text-xs mt-2">{error}</p>}
        </>
      )}
    </div>
  );
}

// ── DatasetPill ────────────────────────────────────────────────────────────

function DatasetPill({ dataset }) {
  if (!dataset) return null;
  const cols = Object.keys(dataset.schema?.columns || {});
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs">
      <p className="font-semibold text-blue-800">{dataset.name}</p>
      <p className="text-blue-600">{dataset.row_count} rows · {cols.slice(0, 4).join(", ")}{cols.length > 4 ? "…" : ""}</p>
    </div>
  );
}

// ── Message ────────────────────────────────────────────────────────────────

function Message({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm
          ${isUser
            ? "bg-blue-600 text-white"
            : "bg-white border border-gray-200 text-gray-800 shadow-sm"}`}
      >
        {isUser ? (
          <p>{msg.content}</p>
        ) : (
          <>
            {msg.content && (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            )}
            {msg.chartSpec && <PlotlyChart spec={msg.chartSpec} />}
            {/* Dashboard grid — shown when agent returns multiple charts */}
            {msg.dashboardSpecs && msg.dashboardSpecs.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                {msg.dashboardSpecs.map((spec, i) => (
                  <PlotlyChart key={i} spec={spec} />
                ))}
              </div>
            )}
            <div className="mt-2 flex gap-3 text-xs text-gray-400">
              {msg.runId && (
                <a href={`http://localhost:8001/traces`} target="_blank" rel="noreferrer"
                  className="underline hover:text-blue-500">trace</a>
              )}
              {msg.cost != null && (
                <span>${msg.cost.toFixed(5)} · {(msg.inputTokens || 0) + (msg.outputTokens || 0)} tok</span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── SessionHeader ──────────────────────────────────────────────────────────

function SessionHeader({ dataset, threadCost, threadTokens, onNewSession }) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b bg-white text-xs text-gray-500">
      <div className="flex gap-4 items-center">
        <span className="font-semibold text-gray-700">
          {dataset ? `Dataset: ${dataset.name}` : "No dataset"}
        </span>
        {threadTokens > 0 && (
          <span>{threadTokens.toLocaleString()} tok · ${threadCost.toFixed(5)}</span>
        )}
      </div>
      <button onClick={onNewSession}
        className="text-gray-400 hover:text-red-500 underline">
        New session
      </button>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function Page() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [dataset, setDataset] = useState(null);
  const [threadId, setThreadId] = useState(null);
  const [threadCost, setThreadCost] = useState(0);
  const [threadTokens, setThreadTokens] = useState(0);
  const [datasets, setDatasets] = useState([]);
  const [stubMode, setStubMode] = useState(false);
  const bottomRef = useRef(null);

  // Restore session from localStorage
  useEffect(() => {
    // Health ping — check stub_mode
    fetch(`${API}/health`).then(r => r.json()).then(body => {
      if (body.ok) setStubMode(body.data.stub_mode === true);
    }).catch(() => {});

    const tid = getOrCreate("thread_id", genId);
    setThreadId(tid);
    const did = ls.get("dataset_id");
    if (did) {
      fetch(`${API}/datasets`).then(r => r.json()).then(body => {
        if (!body.ok) return;
        setDatasets(body.data);
        const found = body.data.find(d => d.dataset_id === did);
        if (found) setDataset(found);
      }).catch(() => {});
    }
    // Restore thread cost
    if (tid) {
      fetch(`${API}/threads/${tid}`).then(r => r.json()).then(body => {
        if (body.ok) {
          setThreadTokens(body.data.total_tokens || 0);
          setThreadCost(body.data.total_cost_usd || 0);
        }
      }).catch(() => {});
    }
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleUploaded = useCallback((ds) => {
    setDataset(ds);
    ls.set("dataset_id", ds.dataset_id);
    setDatasets(prev => [ds, ...prev.filter(d => d.dataset_id !== ds.dataset_id)]);
    setMessages(prev => [...prev, {
      id: genId(), role: "assistant",
      content: `**${ds.name}** uploaded — ${ds.row_count.toLocaleString()} rows.\n\n` +
        `Columns: ${Object.keys(ds.schema?.columns || {}).join(", ")}\n\nYou can now ask questions about this dataset.`,
    }]);
  }, []);

  const send = useCallback(async () => {
    if (!input.trim() || sending) return;
    const goal = input.trim();
    setInput("");
    setSending(true);

    const userMsg = { id: genId(), role: "user", content: goal };
    setMessages(prev => [...prev, userMsg]);

    try {
      const body = { goal, thread_id: threadId };
      if (dataset?.dataset_id) body.dataset_id = dataset.dataset_id;

      const res = await fetch(`${API}/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json();

      if (!json.ok) throw new Error(json.error || "Request failed");
      const d = json.data;

      const agentMsg = {
        id: genId(), role: "assistant",
        content: d.answer || null,
        chartSpec: d.chart_spec || null,
        dashboardSpecs: d.dashboard_specs || [],
        runId: d.run_id,
        cost: d.cost_usd,
        inputTokens: d.input_tokens,
        outputTokens: d.output_tokens,
      };
      setMessages(prev => [...prev, agentMsg]);
      setThreadCost(c => c + (d.cost_usd || 0));
      setThreadTokens(t => t + (d.input_tokens || 0) + (d.output_tokens || 0));
    } catch (e) {
      setMessages(prev => [...prev, { id: genId(), role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setSending(false);
    }
  }, [input, sending, threadId, dataset]);

  const newSession = useCallback(() => {
    const tid = genId();
    ls.set("thread_id", tid);
    ls.remove("dataset_id");
    setThreadId(tid);
    setDataset(null);
    setMessages([]);
    setThreadCost(0);
    setThreadTokens(0);
  }, []);

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto">
      <SessionHeader
        dataset={dataset}
        threadCost={threadCost}
        threadTokens={threadTokens}
        onNewSession={newSession}
      />

      {stubMode && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-1 text-xs text-yellow-700 font-medium text-center">
          STUB MODE — No API key. Responses are scripted. Set ANALYST_LLM_API_KEY to enable live AI.
        </div>
      )}

      <div className="flex flex-1 min-h-0 gap-0">
        {/* Sidebar */}
        <div className="w-72 shrink-0 border-r bg-white p-4 overflow-y-auto flex flex-col gap-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-2">Upload Dataset</h2>
            <UploadPanel onUploaded={handleUploaded} />
          </div>

          {dataset && (
            <div>
              <h2 className="text-sm font-semibold text-gray-700 mb-2">Active Dataset</h2>
              <DatasetPill dataset={dataset} />
            </div>
          )}

          {datasets.length > 1 && (
            <div>
              <h2 className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wide">All Datasets</h2>
              <div className="flex flex-col gap-2">
                {datasets.map(ds => (
                  <button
                    key={ds.dataset_id}
                    onClick={() => {
                      setDataset(ds);
                      ls.set("dataset_id", ds.dataset_id);
                    }}
                    className={`text-left text-xs rounded-lg px-3 py-2 border transition-colors
                      ${dataset?.dataset_id === ds.dataset_id
                        ? "bg-blue-100 border-blue-300 text-blue-800"
                        : "border-gray-200 hover:border-blue-200 text-gray-600"}`}
                  >
                    {ds.name} <span className="text-gray-400">({ds.row_count} rows)</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-auto pt-4 border-t">
            <a
              href="http://localhost:8001/traces"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-blue-500 underline"
            >
              View all traces →
            </a>
          </div>
        </div>

        {/* Chat */}
        <div className="flex flex-col flex-1 min-w-0">
          <div className="flex-1 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="h-full flex items-center justify-center text-gray-400 text-sm text-center">
                <div>
                  <p className="text-2xl mb-2">📊</p>
                  <p>Upload a CSV or JSON file, then ask questions in natural language.</p>
                  <p className="mt-1 text-xs">You can also request charts: "show revenue by region as a bar chart"</p>
                </div>
              </div>
            )}
            {messages.map(msg => <Message key={msg.id} msg={msg} />)}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="border-t bg-white px-4 py-3 flex gap-2">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
              placeholder={dataset ? `Ask about ${dataset.name}…` : "Upload a dataset first, then ask questions"}
              disabled={sending}
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm
                focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
              aria-label="goal"
            />
            <button
              onClick={send}
              disabled={sending || !input.trim()}
              className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium
                hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              aria-label="Send"
            >
              {sending ? "…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
