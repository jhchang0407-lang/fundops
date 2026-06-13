/**
 * ⌘K command palette: typed intent from anywhere — navigate, act, or hand a
 * question to the conversation (free text prefills the Home thread).
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { exportUrls, runDailySync, runPipeline } from '../api/client';

interface Command {
  label: string;
  hint?: string;
  run: () => void;
}

export function prefillConversation(text: string) {
  window.dispatchEvent(new CustomEvent('fundops:prefill', { detail: text }));
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const pipeline = useMutation({ mutationFn: runPipeline });
  const sync = useMutation({ mutationFn: runDailySync });

  const commands: Command[] = useMemo(
    () => [
      { label: 'Go to Home', run: () => navigate('/') },
      { label: 'Go to Inbox', run: () => navigate('/inbox') },
      { label: 'Go to Runs', run: () => navigate('/runs') },
      { label: 'Go to Markets', run: () => navigate('/markets') },
      { label: 'Go to Portfolio', run: () => navigate('/portfolio') },
      { label: 'Go to Library', run: () => navigate('/library') },
      { label: 'Go to Settings', run: () => navigate('/settings') },
      {
        label: 'Run full pipeline',
        hint: 'screener → thesis → IC → memo',
        run: () => { pipeline.mutate(); navigate('/runs'); },
      },
      { label: 'Sync data now', hint: 'daily tick', run: () => sync.mutate() },
      {
        label: 'Export portfolio CSV',
        run: () => { window.location.href = exportUrls.portfolio; },
      },
    ],
    [navigate, pipeline, sync],
  );

  const filtered = q.trim()
    ? commands.filter((c) => c.label.toLowerCase().includes(q.trim().toLowerCase()))
    : commands;

  useEffect(() => {
    if (open) {
      setQ('');
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  if (!open) return null;

  const freeAsk = () => {
    const text = q.trim();
    if (!text) return;
    onClose();
    navigate('/');
    setTimeout(() => prefillConversation(text), 80);
  };

  return (
    <div className="panel-overlay" onClick={onClose} style={{ alignItems: 'flex-start', paddingTop: '12vh' }}>
      <div className="panel-sheet" style={{ width: 540 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ padding: '12px 14px 8px' }}>
          <input
            ref={inputRef}
            className="editor-input"
            style={{ width: '100%', fontSize: 'var(--text-base)' }}
            placeholder="Type a command — or ask anything and press Enter…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                if (filtered.length > 0 && commands.includes(filtered[0]) && q.trim() && filtered[0].label.toLowerCase().includes(q.trim().toLowerCase())) {
                  filtered[0].run();
                  onClose();
                } else {
                  freeAsk();
                }
              }
              if (e.key === 'Escape') onClose();
            }}
          />
        </div>
        <div style={{ padding: '0 8px 10px', maxHeight: '46vh', overflowY: 'auto' }}>
          {filtered.map((c) => (
            <button
              key={c.label}
              onClick={() => { c.run(); onClose(); }}
              style={{
                display: 'flex', width: '100%', alignItems: 'baseline', gap: 10,
                textAlign: 'left', padding: '8px 10px', borderRadius: 'var(--radius-md)',
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 'var(--text-sm)', color: 'var(--text-primary)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--well)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
            >
              {c.label}
              {c.hint && (
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{c.hint}</span>
              )}
            </button>
          ))}
          {q.trim() && (
            <button
              onClick={freeAsk}
              style={{
                display: 'flex', width: '100%', gap: 8, textAlign: 'left', padding: '8px 10px',
                borderRadius: 'var(--radius-md)', background: 'var(--teal-bg)', border: 'none',
                cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--teal-ink)', marginTop: 4,
              }}
            >
              Ask the conversation: “{q.trim()}”
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
