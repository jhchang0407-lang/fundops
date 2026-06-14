/**
 * Point-at-anything: the chat comes to the object. Call `ask(event, subject)`
 * from any clickable number/row and an anchored popover offers questions
 * born from that object. Choosing one opens the companion and sends the
 * question through the REAL analyst (tools answer it from local data).
 */

import { useEffect, useState } from 'react';
import { queueSend } from './chat/ChatThread';

export interface AskSubject {
  title: string;                    // "AXON · ROIC 18.4%"
  questions: string[];              // fully-formed, analyst-ready
  /** Selected passage (artifact reader): sent with every question so the
   * analyst knows exactly what "this" refers to. */
  quote?: string;
}

interface PopState extends AskSubject {
  x: number;
  y: number;
}

export function ask(e: React.MouseEvent, subject: AskSubject) {
  e.stopPropagation();
  window.dispatchEvent(
    new CustomEvent<PopState>('fundops:askpop', {
      detail: { ...subject, x: e.clientX, y: e.clientY },
    }),
  );
}

/** Open the ask popover at explicit coordinates (e.g. near a text selection). */
export function askAt(x: number, y: number, subject: AskSubject) {
  window.dispatchEvent(
    new CustomEvent<PopState>('fundops:askpop', { detail: { ...subject, x, y } }),
  );
}

/** Standard question set for a (ticker, metric) pair — routed to real tools. */
export function metricQuestions(ticker: string, label: string, value: string): string[] {
  return [
    `Why is ${ticker}'s ${label.toLowerCase()} ${value}?`,
    `Compare ${ticker} with its peers on ${label.toLowerCase()}`,
    `Show ${ticker}'s ${label.toLowerCase()} history`,
  ];
}

export function AskPopover() {
  const [pop, setPop] = useState<PopState | null>(null);
  const [free, setFree] = useState('');

  useEffect(() => {
    const onOpen = (e: Event) => {
      setFree('');
      setPop((e as CustomEvent<PopState>).detail);
    };
    const onClose = () => setPop(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('fundops:askpop', onOpen);
    window.addEventListener('click', onClose);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('fundops:askpop', onOpen);
      window.removeEventListener('click', onClose);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  if (!pop) return null;

  const fire = (q: string) => {
    setPop(null);
    // A selected passage rides along so the analyst knows what "this" means.
    const message = pop.quote
      ? `${q}\n\nSelected passage (from the document I'm reading): “${pop.quote}”`
      : q;
    // Open the companion (no-op on Home where the thread is inline)…
    window.dispatchEvent(new CustomEvent('fundops:companion', { detail: 'open' }));
    // …and queue the send: delivered immediately if a thread is mounted,
    // else consumed by the thread the moment it mounts (no timing race).
    setTimeout(() => queueSend(message), 60);
  };

  const left = Math.min(pop.x, window.innerWidth - 300);
  const top = Math.min(pop.y + 10, window.innerHeight - 230);

  return (
    <div
      className="ask-popover"
      style={{ left, top }}
      onClick={(e) => e.stopPropagation()}
    >
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 7 }}>
        {pop.title}
      </div>
      {pop.questions.map((q) => (
        <button key={q} className="ask-suggestion" onClick={() => fire(q)}>
          <span style={{ color: 'var(--teal)' }}>✦</span> {q}
        </button>
      ))}
      <div style={{ display: 'flex', gap: 6, marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--hairline)' }}>
        <input
          className="editor-input"
          style={{ flex: 1, fontSize: 'var(--text-xs)', padding: '4px 9px' }}
          placeholder="Or ask anything about this…"
          value={free}
          onChange={(e) => setFree(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && free.trim()) fire(`${free.trim()} (${pop.title})`);
          }}
        />
        <button
          className="btn btn-accent"
          style={{ fontSize: 'var(--text-xs)', padding: '3px 10px' }}
          disabled={!free.trim()}
          onClick={() => fire(`${free.trim()} (${pop.title})`)}
        >
          Ask
        </button>
      </div>
    </div>
  );
}
