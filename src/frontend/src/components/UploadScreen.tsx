import { useState, useCallback } from 'react';
import { uploadFile, type SessionInfo } from '../api';

interface Props {
  onSessionReady: (session: SessionInfo) => void;
  onCancel?: () => void;
}

export function UploadScreen({ onSessionReady, onCancel }: Props) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleFile = useCallback(async (file: File) => {
    setError('');
    setLoading(true);
    try {
      const session = await uploadFile(file);
      if (session.status === 'error') {
        setError(session.error_message || 'Failed to parse file');
      } else {
        onSessionReady(session);
      }
    } catch (e: any) {
      setError(e.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  }, [onSessionReady]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '40px',
    }}>
      <h1 style={{ fontSize: '28px', marginBottom: '8px' }}>DataChat</h1>
      <p style={{ color: '#666', marginBottom: '32px' }}>
        Upload a CSV or JSON file and ask questions about your data
      </p>

      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{
          border: `2px dashed ${dragging ? '#2563eb' : '#ccc'}`,
          borderRadius: '12px',
          padding: '60px 80px',
          textAlign: 'center',
          cursor: loading ? 'wait' : 'pointer',
          background: dragging ? '#eff6ff' : '#fff',
          transition: 'all 0.2s',
          minWidth: '340px',
        }}
      >
        <input type="file" accept=".csv,.json" onChange={onInputChange} style={{ display: 'none' }} disabled={loading} />
        {loading ? (
          <p style={{ fontSize: '16px', color: '#555' }}>Uploading & parsing…</p>
        ) : (
          <>
            <p style={{ fontSize: '40px', marginBottom: '12px' }}>📂</p>
            <p style={{ fontSize: '16px', fontWeight: 600 }}>Drop your file here</p>
            <p style={{ fontSize: '13px', color: '#888', marginTop: '6px' }}>CSV or JSON · up to 50MB</p>
            <div style={{
              marginTop: '20px', padding: '8px 20px', background: '#2563eb',
              color: '#fff', borderRadius: '6px', display: 'inline-block', fontSize: '14px',
            }}>
              Browse files
            </div>
          </>
        )}
      </label>

      {error && (
        <p style={{ color: '#dc2626', marginTop: '16px', fontSize: '14px' }}>{error}</p>
      )}

      {onCancel && (
        <button
          onClick={onCancel}
          style={{
            marginTop: '20px', background: 'none', border: 'none',
            color: '#64748b', cursor: 'pointer', fontSize: '14px',
          }}
        >
          ← Back to sessions
        </button>
      )}
    </div>
  );
}
