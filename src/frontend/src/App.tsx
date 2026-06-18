import { useState, useEffect, useCallback } from 'react';
import { UploadScreen } from './components/UploadScreen';
import { ChatScreen } from './components/ChatScreen';
import { StubBanner } from './components/StubBanner';
import { getHealth, listSessions, deleteSession, type SessionInfo } from './api';

type View = 'home' | 'upload' | 'chat';

function fmt(n: number): string {
  return n.toLocaleString();
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function App() {
  const [view, setView] = useState<View>('home');
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeSession, setActiveSession] = useState<SessionInfo | null>(null);
  const [sessionTokensIn, setSessionTokensIn] = useState(0);
  const [sessionTokensOut, setSessionTokensOut] = useState(0);
  const [llmProvider, setLlmProvider] = useState('stub');
  const [loadingList, setLoadingList] = useState(false);

  const refreshSessions = useCallback(() => {
    setLoadingList(true);
    listSessions()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoadingList(false));
  }, []);

  useEffect(() => {
    getHealth().then(h => setLlmProvider(h.llm_provider)).catch(() => {});
    refreshSessions();
  }, [refreshSessions]);

  const openSession = (s: SessionInfo) => {
    setActiveSession(s);
    setSessionTokensIn(s.total_tokens_input ?? 0);
    setSessionTokensOut(s.total_tokens_output ?? 0);
    setView('chat');
  };

  const handleUploadDone = (s: SessionInfo) => {
    setSessions(prev => [{ ...s, message_count: 0, total_tokens_input: 0, total_tokens_output: 0 }, ...prev]);
    setActiveSession(s);
    setSessionTokensIn(0);
    setSessionTokensOut(0);
    setView('chat');
  };

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    await deleteSession(sessionId);
    setSessions(prev => prev.filter(s => s.session_id !== sessionId));
    if (activeSession?.session_id === sessionId) {
      setActiveSession(null);
      setView('home');
    }
  };

  const handleTokensAdded = (input: number, output: number) => {
    setSessionTokensIn(prev => prev + input);
    setSessionTokensOut(prev => prev + output);
  };

  return (
    <>
      <StubBanner provider={llmProvider} />

      {view === 'home' && (
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Left rail */}
          <div style={{
            width: '260px', background: '#1e293b', color: '#fff',
            padding: '24px 16px', display: 'flex', flexDirection: 'column', flexShrink: 0,
          }}>
            <div style={{ fontSize: '20px', fontWeight: 700, marginBottom: '4px' }}>DataChat</div>
            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '28px' }}>AI Data Assistant</div>

            <button
              onClick={() => setView('upload')}
              style={{
                padding: '10px 16px', background: '#2563eb', color: '#fff',
                border: 'none', borderRadius: '8px', cursor: 'pointer',
                fontSize: '14px', fontWeight: 600, width: '100%',
              }}
            >
              + New session
            </button>
          </div>

          {/* Session list */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px', background: '#f8fafc' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
              <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#1e293b' }}>
                Sessions
              </h2>
              <button
                onClick={refreshSessions}
                disabled={loadingList}
                style={{
                  background: 'none', border: '1px solid #e2e8f0', borderRadius: '6px',
                  padding: '4px 10px', fontSize: '12px', color: '#64748b', cursor: 'pointer',
                }}
              >
                {loadingList ? '…' : '↻ Refresh'}
              </button>
            </div>

            {sessions.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#94a3b8', marginTop: '80px' }}>
                <p style={{ fontSize: '32px', marginBottom: '8px' }}>📂</p>
                <p style={{ fontSize: '16px', fontWeight: 500 }}>No sessions yet</p>
                <p style={{ fontSize: '14px', marginTop: '4px' }}>
                  Upload a CSV or JSON file to start analysing
                </p>
                <button
                  onClick={() => setView('upload')}
                  style={{
                    marginTop: '16px', padding: '10px 24px', background: '#2563eb',
                    color: '#fff', border: 'none', borderRadius: '8px',
                    cursor: 'pointer', fontSize: '14px', fontWeight: 600,
                  }}
                >
                  Upload file
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '720px' }}>
                {sessions.map(s => (
                  <div
                    key={s.session_id}
                    onClick={() => openSession(s)}
                    style={{
                      background: '#fff', borderRadius: '12px', padding: '16px 20px',
                      border: '1px solid #e2e8f0', cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: '16px',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                      transition: 'box-shadow 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)')}
                    onMouseLeave={e => (e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)')}
                  >
                    <div style={{
                      width: '40px', height: '40px', background: '#eff6ff',
                      borderRadius: '10px', display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: '18px', flexShrink: 0,
                    }}>
                      📊
                    </div>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: '15px', fontWeight: 600, color: '#1e293b',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {s.filename}
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                        {s.row_count.toLocaleString()} rows ·{' '}
                        {s.message_count ? `${Math.floor((s.message_count ?? 0) / 2)} queries` : 'no queries yet'} ·{' '}
                        {s.last_active_at ? timeAgo(s.last_active_at) : ''}
                      </div>
                    </div>

                    {((s.total_tokens_input ?? 0) + (s.total_tokens_output ?? 0)) > 0 && (
                      <div style={{
                        fontSize: '11px', color: '#94a3b8', textAlign: 'right', flexShrink: 0,
                      }}>
                        <div style={{ color: '#60a5fa', fontWeight: 600, fontFamily: 'monospace' }}>
                          {fmt((s.total_tokens_input ?? 0) + (s.total_tokens_output ?? 0))} tok
                        </div>
                        <div>session total</div>
                      </div>
                    )}

                    <button
                      onClick={e => handleDelete(e, s.session_id)}
                      title="Delete session"
                      style={{
                        background: 'none', border: '1px solid #fee2e2', borderRadius: '6px',
                        padding: '4px 8px', cursor: 'pointer', color: '#ef4444',
                        fontSize: '12px', flexShrink: 0,
                      }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {view === 'upload' && (
        <UploadScreen
          onSessionReady={handleUploadDone}
          onCancel={sessions.length > 0 ? () => setView('home') : undefined}
        />
      )}

      {view === 'chat' && activeSession && (
        <ChatScreen
          session={activeSession}
          onReset={() => { refreshSessions(); setView('home'); }}
          sessionTokensInput={sessionTokensIn}
          sessionTokensOutput={sessionTokensOut}
          onTokensAdded={handleTokensAdded}
        />
      )}
    </>
  );
}
