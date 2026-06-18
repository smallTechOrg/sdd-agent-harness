import { useState, useRef, useEffect, useCallback } from 'react';
import { askQuestion, getMessages, type SessionInfo, type AskResponse } from '../api';

interface Step {
  action: string;
  result: string;
  is_error: boolean;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  steps?: Step[];
  iterationCount?: number;
  tokensInput?: number;
  tokensOutput?: number;
  firedAt?: string;
  durationMs?: number;
}

interface Props {
  session: SessionInfo;
  onReset: () => void;
  sessionTokensInput: number;
  sessionTokensOutput: number;
  onTokensAdded: (input: number, output: number) => void;
}

function fmt(n: number): string {
  return n.toLocaleString();
}

function ElapsedTimer({ startMs }: { startMs: number }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Date.now() - startMs), 250);
    return () => clearInterval(id);
  }, [startMs]);
  const s = (elapsed / 1000).toFixed(1);
  return <span style={{ fontVariantNumeric: 'tabular-nums' }}>{s}s</span>;
}

export function ChatScreen({ session, onReset, sessionTokensInput, sessionTokensOutput, onTokensAdded }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStart, setLoadingStart] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getMessages(session.session_id).then(msgs => {
      setMessages(msgs.map(m => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
        steps: m.reasoning_trace ?? undefined,
        iterationCount: m.iteration_count ?? undefined,
        tokensInput: m.tokens_input,
        tokensOutput: m.tokens_output,
        firedAt: m.created_at,
      })));
    }).catch(() => {});
  }, [session.session_id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setError('');
    const firedAt = new Date().toISOString();
    setMessages(prev => [...prev, { role: 'user', content: q, firedAt }]);
    setLoading(true);
    setLoadingStart(Date.now());
    const t0 = Date.now();
    try {
      const resp: AskResponse = await askQuestion(session.session_id, q);
      const durationMs = Date.now() - t0;
      onTokensAdded(resp.tokens_input, resp.tokens_output);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: resp.answer,
        steps: resp.reasoning_trace,
        iterationCount: resp.iteration_count,
        tokensInput: resp.tokens_input,
        tokensOutput: resp.tokens_output,
        firedAt: new Date().toISOString(),
        durationMs,
      }]);
    } catch (e: unknown) {
      setError((e as Error).message || 'Something went wrong');
    } finally {
      setLoading(false);
      setLoadingStart(null);
    }
  }, [input, loading, session.session_id, onTokensAdded]);

  const toggleSteps = (i: number) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  };

  const totalIn = sessionTokensInput;
  const totalOut = sessionTokensOutput;

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      {/* Sidebar */}
      <div style={{
        width: '240px', background: '#1e293b', color: '#fff',
        padding: '20px 16px', display: 'flex', flexDirection: 'column', flexShrink: 0,
        overflowY: 'auto',
      }}>
        <div style={{ fontSize: '18px', fontWeight: 700, marginBottom: '4px' }}>DataChat</div>
        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '24px' }}>AI Data Assistant</div>

        <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
          Current file
        </div>
        <div style={{ fontSize: '13px', fontWeight: 600, wordBreak: 'break-all' }}>{session.filename}</div>
        <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>{session.row_count.toLocaleString()} rows</div>

        <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', marginTop: '20px', marginBottom: '6px' }}>
          Columns ({session.column_names.length})
        </div>
        <div style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: '1.8', maxHeight: '140px', overflow: 'auto' }}>
          {session.column_names.map(c => <div key={c} style={{ fontFamily: 'monospace' }}>{c}</div>)}
        </div>

        {/* Session token totals */}
        <div style={{
          marginTop: '20px', background: '#0f172a', borderRadius: '8px',
          padding: '10px 12px',
        }}>
          <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', marginBottom: '6px' }}>
            Session tokens
          </div>
          <div style={{ fontSize: '12px', color: '#94a3b8', lineHeight: '1.8' }}>
            <div>In: <span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{fmt(totalIn)}</span></div>
            <div>Out: <span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{fmt(totalOut)}</span></div>
            <div>Total: <span style={{ color: '#60a5fa', fontFamily: 'monospace', fontWeight: 600 }}>{fmt(totalIn + totalOut)}</span></div>
          </div>
        </div>

        <button
          onClick={onReset}
          style={{
            marginTop: '16px', padding: '8px', background: '#334155',
            color: '#cbd5e1', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px',
          }}
        >
          ← All sessions
        </button>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: '#999', marginTop: '60px' }}>
              <p style={{ fontSize: '20px' }}>👋</p>
              <p style={{ marginTop: '8px' }}>Ask anything about <strong>{session.filename}</strong></p>
              <p style={{ fontSize: '13px', color: '#bbb', marginTop: '4px' }}>
                e.g. "What is the average value?", "Show the top 5 rows", "Any outliers?"
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ marginBottom: '20px' }}>
              {/* Timestamp row */}
              {msg.firedAt && (
                <div style={{
                  fontSize: '11px', color: '#9ca3af',
                  textAlign: msg.role === 'user' ? 'right' : 'left',
                  marginBottom: '4px',
                }}>
                  {new Date(msg.firedAt).toLocaleTimeString()}
                  {msg.durationMs !== undefined && (
                    <span style={{ marginLeft: '6px', color: '#6b7280' }}>
                      ({(msg.durationMs / 1000).toFixed(1)}s)
                    </span>
                  )}
                </div>
              )}

              <div style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{
                  maxWidth: '72%',
                  background: msg.role === 'user' ? '#2563eb' : '#fff',
                  color: msg.role === 'user' ? '#fff' : '#222',
                  borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                  padding: '12px 16px',
                  fontSize: '14px',
                  lineHeight: '1.6',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                </div>
              </div>

              {/* Token count for assistant messages */}
              {msg.role === 'assistant' && (msg.tokensInput !== undefined || msg.tokensOutput !== undefined) && (
                <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '4px', paddingLeft: '2px' }}>
                  Tokens — in: {fmt(msg.tokensInput ?? 0)} · out: {fmt(msg.tokensOutput ?? 0)} · total: {fmt((msg.tokensInput ?? 0) + (msg.tokensOutput ?? 0))}
                </div>
              )}

              {/* Script log (collapsible) */}
              {msg.role === 'assistant' && msg.steps && msg.steps.length > 0 && (
                <div style={{ marginTop: '6px', paddingLeft: '4px' }}>
                  <button
                    onClick={() => toggleSteps(i)}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      fontSize: '12px', color: '#64748b', padding: '2px 4px',
                    }}
                  >
                    {expandedSteps.has(i) ? '▼' : '▶'} Script log ({msg.steps.length} step{msg.steps.length !== 1 ? 's' : ''})
                  </button>

                  {expandedSteps.has(i) && (
                    <div style={{
                      marginTop: '6px', background: '#0f172a', border: '1px solid #1e293b',
                      borderRadius: '8px', padding: '12px', fontSize: '12px', fontFamily: 'monospace',
                    }}>
                      {msg.steps.map((step, j) => (
                        <div key={j} style={{ marginBottom: '12px' }}>
                          <div style={{ color: '#7dd3fc', marginBottom: '2px' }}>
                            # Step {j + 1}
                          </div>
                          <div style={{ color: '#a3e635' }}>
                            df.{step.action}
                          </div>
                          <div style={{
                            color: step.is_error ? '#f87171' : '#94a3b8',
                            marginTop: '4px',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-all',
                            maxHeight: '120px',
                            overflow: 'auto',
                            paddingLeft: '8px',
                            borderLeft: `2px solid ${step.is_error ? '#ef4444' : '#334155'}`,
                          }}>
                            {step.result.slice(0, 500)}{step.result.length > 500 ? '…' : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div style={{ color: '#888', fontSize: '14px', display: 'flex', gap: '8px', alignItems: 'center' }}>
              <span>Analysing</span>
              {loadingStart && <ElapsedTimer startMs={loadingStart} />}
            </div>
          )}

          {error && (
            <div style={{ color: '#dc2626', fontSize: '13px', padding: '8px 12px', background: '#fef2f2', borderRadius: '6px' }}>
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div style={{
          padding: '16px 32px', background: '#fff', borderTop: '1px solid #e5e7eb',
          display: 'flex', gap: '10px',
        }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="Ask a question about your data…"
            disabled={loading}
            style={{
              flex: 1, padding: '10px 14px', border: '1px solid #d1d5db',
              borderRadius: '8px', fontSize: '14px', outline: 'none',
            }}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            style={{
              padding: '10px 20px', background: loading ? '#93c5fd' : '#2563eb',
              color: '#fff', border: 'none', borderRadius: '8px',
              cursor: loading ? 'not-allowed' : 'pointer', fontSize: '14px', fontWeight: 600,
            }}
          >
            {loading ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
