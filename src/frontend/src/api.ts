const BASE = 'http://localhost:8001';

export interface SessionInfo {
  session_id: string;
  filename: string;
  status: string;
  row_count: number;
  column_names: string[];
  message_count?: number;
  total_tokens_input?: number;
  total_tokens_output?: number;
  created_at?: string;
  last_active_at?: string;
  error_message?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning_trace?: { action: string; result: string; is_error: boolean }[];
  iteration_count?: number;
  tokens_input?: number;
  tokens_output?: number;
  created_at: string;
}

export interface HealthInfo {
  status: string;
  version: string;
  llm_provider: string;
}

export interface AskResponse {
  answer: string;
  reasoning_trace: { action: string; result: string; is_error: boolean }[];
  iteration_count: number;
  tokens_input: number;
  tokens_output: number;
  llm_provider: string;
}

export async function getHealth(): Promise<HealthInfo> {
  const r = await fetch(`${BASE}/health`);
  const j = await r.json();
  return j.data;
}

export async function uploadFile(file: File): Promise<SessionInfo> {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`${BASE}/api/sessions`, { method: 'POST', body: form });
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail?.message || 'Upload failed');
  return j.data;
}

export async function listSessions(): Promise<SessionInfo[]> {
  const r = await fetch(`${BASE}/api/sessions`);
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail?.message || 'Failed to load sessions');
  return j.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const r = await fetch(`${BASE}/api/sessions/${sessionId}`, { method: 'DELETE' });
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail?.message || 'Delete failed');
}

export async function askQuestion(sessionId: string, question: string): Promise<AskResponse> {
  const r = await fetch(`${BASE}/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail?.message || 'Request failed');
  return j.data;
}

export async function getMessages(sessionId: string): Promise<Message[]> {
  const r = await fetch(`${BASE}/api/sessions/${sessionId}/messages`);
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail?.message || 'Failed to load messages');
  return j.data;
}
