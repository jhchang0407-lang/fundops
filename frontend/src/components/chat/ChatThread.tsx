/**
 * The chat conversation thread — message bubbles, draft cards, data blocks,
 * citation/action pills, and the input bar — shared between the full Chat
 * page (variant="page") and the ambient drawer on other pages
 * (variant="drawer", with the page's context injected into each message).
 *
 * Live Strategy Chat Session continuity (CONTEXT: the chat must persist
 * across tab/page changes while the local app keeps running): the live
 * thread is held in a module-level store keyed by session id, shared by both
 * variants, so the drawer and /chat are one conversation. A true page reload
 * re-seeds from server history; with no local session id the server-side
 * anchor (GET /chat/session) resumes the latest conversation.
 */

import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import {
  sendChat,
  getChatHistory,
  getChatSession,
  getStrategy,
  acceptProposal,
  rejectProposal,
  directedResearch,
  runPipeline,
  runScreener,
} from '../../api/client';
import type {
  ChatAction,
  ChatBlock,
  ChatCitation,
  ChatHistoryMessage,
  ChatPageContext,
  ProposalCard,
} from '../../api/client';
import { DraftCard } from './DraftCard';
import type { DraftResolution } from './DraftCard';
import { ChatBlocks } from './blocks';
import { humanize } from './criterionDisplay';

const SESSION_KEY = 'fundops.chat.session_id';

export interface Msg {
  role: 'user' | 'assistant';
  mode?: string | null;
  content: string;
  draft?: ProposalCard;
  citations?: ChatCitation[];
  actions?: ChatAction[];
  blocks?: ChatBlock[];
  created_at?: string;
  /** Loaded from server history (draft buttons gated on pending state). */
  fromHistory?: boolean;
  /** Locally generated notice (approval confirmations, errors). */
  local?: boolean;
}

interface LiveThread {
  messages: Msg[];
  resolutions: Record<string, DraftResolution>;
}
const liveThreads = new Map<string, LiveThread>();

// Send queued by a popover before any ChatThread is mounted (the companion
// opens and mounts in the same gesture). Consumed once by the first thread
// whose send listener comes up; the event path handles the already-mounted case.
let pendingSend: string | null = null;

/** Fire-and-forget send that survives the companion's mount race. */
export function queueSend(text: string) {
  pendingSend = text;
  window.dispatchEvent(new CustomEvent('fundops:send', { detail: text }));
}

function getLiveThread(sessionId: string | null): LiveThread | null {
  return sessionId ? liveThreads.get(sessionId) ?? null : null;
}

function saveLiveThread(sessionId: string | null, thread: LiveThread): void {
  if (sessionId) liveThreads.set(sessionId, thread);
}

function renderMarkdown(text: string): string {
  const html = marked.parse(text, { breaks: true, async: false }) as string;
  return DOMPurify.sanitize(html);
}

function parseHistory(rows: ChatHistoryMessage[]): Msg[] {
  return rows.map((r) => {
    let refs: unknown = r.refs ?? null;
    if (typeof refs === 'string') {
      try {
        refs = JSON.parse(refs);
      } catch {
        refs = null;
      }
    }
    let citations: ChatCitation[] | undefined;
    let actions: ChatAction[] | undefined;
    let draft: ProposalCard | undefined;
    let blocks: ChatBlock[] | undefined;
    if (Array.isArray(refs)) {
      citations = refs as ChatCitation[];
    } else if (refs && typeof refs === 'object') {
      const obj = refs as {
        citations?: ChatCitation[];
        actions?: ChatAction[];
        draft?: ProposalCard | null;
        blocks?: ChatBlock[];
      };
      // Older messages stored citations as bare artifact-id strings — only
      // replay structured pills.
      citations = obj.citations?.filter((c) => c && typeof c === 'object');
      actions = obj.actions;
      draft = obj.draft ?? undefined;
      blocks = obj.blocks;
    }
    return {
      role: r.role === 'user' ? 'user' : 'assistant',
      mode: r.mode,
      content: r.content,
      citations,
      actions,
      draft,
      blocks,
      created_at: r.created_at,
      fromHistory: true,
    };
  });
}

const MODE_CHIPS: Record<string, { label: string; className: string }> = {
  strategy: { label: 'Strategy', className: 'mode-chip-strategy' },
  archive: { label: 'Archive', className: 'mode-chip-archive' },
  data: { label: 'Data', className: 'mode-chip-data' },
  guide: { label: 'Guide', className: 'mode-chip-data' },
  action: { label: 'Action', className: 'mode-chip-strategy' },
};

/**
 * Pending bubble with an elapsed-time counter and staged status, so a slow
 * provider call (chat can take ~18s) reads as actively working rather than
 * frozen (ISSUE-001). Mounts only while a send is in flight, so its timer
 * lifecycle matches the request. Announced politely for screen readers.
 */
function PendingBubble() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, []);
  const status =
    elapsed < 4 ? 'Thinking…'
      : elapsed < 12 ? 'Working through your data…'
        : 'Still working — the model is taking a little longer…';
  return (
    <div
      className="chat-bubble chat-bubble-assistant"
      style={{ color: 'var(--text-muted)' }}
      role="status"
      aria-live="polite"
    >
      <span
        style={{
          display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
          background: 'var(--accent)', marginRight: 8,
          animation: 'pulse 1.2s ease-in-out infinite',
        }}
      />
      {status}
      {elapsed >= 2 && (
        <span style={{ marginLeft: 8, fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)' }}>
          {elapsed}s
        </span>
      )}
    </div>
  );
}

export function ChatThread({
  variant,
  pageContext,
}: {
  variant: 'page' | 'drawer';
  pageContext?: ChatPageContext | null;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const initialSession = localStorage.getItem(SESSION_KEY);
  const restored = getLiveThread(initialSession);
  const [sessionId, setSessionId] = useState<string | null>(initialSession);
  const [messages, setMessages] = useState<Msg[]>(restored?.messages ?? []);
  const [input, setInput] = useState('');
  const [resolutions, setResolutions] = useState<Record<string, DraftResolution>>(
    restored?.resolutions ?? {},
  );
  // Restored live thread is already the current conversation — don't re-seed.
  const seededRef = useRef(restored != null);
  const anchorTriedRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { data: strategy } = useQuery({ queryKey: ['strategy'], queryFn: getStrategy });

  // Server-side session anchor: a cold start with no local session id adopts
  // the latest server conversation instead of silently minting a new one.
  useEffect(() => {
    if (sessionId || anchorTriedRef.current) return;
    anchorTriedRef.current = true;
    getChatSession()
      .then((r) => {
        if (r.session_id) {
          localStorage.setItem(SESSION_KEY, r.session_id);
          setSessionId(r.session_id);
        }
      })
      .catch(() => {
        /* offline backend — start fresh on first send */
      });
  }, [sessionId]);

  const { data: historyData } = useQuery({
    queryKey: ['chat-history', sessionId],
    queryFn: () => getChatHistory(sessionId!),
    enabled: !!sessionId && !seededRef.current,
    staleTime: Infinity,
  });

  // Cold start (page reload): seed from server history once. Live navigation
  // restores from the module store instead (richer, with drafts).
  useEffect(() => {
    if (!seededRef.current && historyData?.messages?.length) {
      seededRef.current = true;
      setMessages((prev) => (prev.length === 0 ? parseHistory(historyData.messages) : prev));
    }
  }, [historyData]);

  // Persist the live thread on every change so navigating away and back is
  // lossless, and the drawer and /chat stay one conversation.
  useEffect(() => {
    saveLiveThread(sessionId, { messages, resolutions });
  }, [sessionId, messages, resolutions]);

  // Re-adopt thread state written by the other variant (drawer ↔ page).
  useEffect(() => {
    const t = getLiveThread(sessionId);
    if (t && t.messages.length > messages.length) {
      setMessages(t.messages);
      setResolutions(t.resolutions);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  // ⌘K palette and slash chips hand text to the conversation via this event.
  useEffect(() => {
    const onPrefill = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (typeof text === 'string') {
        setInput(text);
        inputRef.current?.focus();
      }
    };
    window.addEventListener('fundops:prefill', onPrefill);
    return () => window.removeEventListener('fundops:prefill', onPrefill);
  }, []);

  const send = useMutation({
    mutationFn: (text: string) => sendChat(text, sessionId, pageContext),
    onSuccess: (res) => {
      if (res.session_id && res.session_id !== sessionId) {
        localStorage.setItem(SESSION_KEY, res.session_id);
        seededRef.current = true; // already showing the live conversation
        setSessionId(res.session_id);
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          mode: res.mode,
          content: res.reply,
          draft: res.draft ?? undefined,
          citations: res.citations,
          actions: res.actions,
          blocks: res.blocks,
        },
      ]);
      if (res.mode === 'strategy') {
        qc.invalidateQueries({ queryKey: ['strategy'] });
      }
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', mode: 'status', local: true, content: `Request failed: ${err.message}` },
      ]);
    },
  });

  const approve = useMutation({
    mutationFn: (draftId: string) => acceptProposal(draftId),
    onSuccess: (res, draftId) => {
      setResolutions((prev) => ({ ...prev, [draftId]: 'accepted' }));
      const vn = res.version?.version_number;
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          mode: 'status',
          local: true,
          content: `Constitution v${vn ?? '—'} is now active. Capability settings were wired from the approved rules — open any capability chip to inspect them.`,
        },
      ]);
      qc.invalidateQueries({ queryKey: ['strategy'] });
      qc.invalidateQueries({ queryKey: ['wiring'] });
      qc.invalidateQueries({ queryKey: ['health'] });
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', mode: 'status', local: true, content: `Approval failed: ${err.message}` },
      ]);
    },
  });

  const reject = useMutation({
    mutationFn: (draftId: string) => rejectProposal(draftId),
    onSuccess: (_res, draftId) => {
      setResolutions((prev) => ({ ...prev, [draftId]: 'rejected' }));
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          mode: 'status',
          local: true,
          content: 'Proposal cancelled. The active Constitution is unchanged.',
        },
      ]);
      qc.invalidateQueries({ queryKey: ['strategy'] });
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', mode: 'status', local: true, content: `Cancel failed: ${err.message}` },
      ]);
    },
  });

  const sendText = (text: string) => {
    if (!text || send.isPending) return;
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    send.mutate(text);
  };

  const submit = () => sendText(input.trim());

  // Point-at-anything popovers send fully-formed questions straight through.
  // A queued send survives the companion's first mount: the popover may fire
  // before this listener exists (the thread mounts when the panel opens), so
  // the pending message is consumed here instead of being lost to timing.
  useEffect(() => {
    const onSend = (e: Event) => {
      pendingSend = null;
      const text = (e as CustomEvent<string>).detail;
      if (typeof text === 'string' && text.trim()) sendText(text.trim());
    };
    window.addEventListener('fundops:send', onSend);
    if (pendingSend) {
      const queued = pendingSend;
      pendingSend = null;
      sendText(queued);
    }
    return () => window.removeEventListener('fundops:send', onSend);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [send.isPending, sessionId, pageContext]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const openCitation = (c: ChatCitation) => {
    if (c.artifact_id) navigate(`/artifact/${c.artifact_id}`);
    else if (c.ticker) navigate(`/company/${c.ticker}`);
  };

  const runAction = (a: ChatAction) => {
    if (a.type === 'open_artifact' && a.id) navigate(`/artifact/${a.id}`);
    else if (a.type === 'open_company' && a.ticker) navigate(`/company/${a.ticker}`);
    else if (a.type === 'navigate' && a.route) navigate(a.route);
    else if (a.type === 'run_directed' && a.ticker && (a.capability === 'thesis' || a.capability === 'memo')) {
      // The click IS the confirmation — chat never starts a run silently.
      const cap = a.capability;
      directedResearch(a.ticker, cap)
        .then(() => navigate(cap === 'thesis' ? '/thesis' : '/memo'))
        .catch((err: Error) => setMessages((prev) => [...prev,
          { role: 'assistant', mode: 'status', local: true,
            content: `Could not start the ${cap} run: ${err.message}` }]));
    } else if (a.type === 'run_workflow') {
      const start = a.kind === 'screener' ? runScreener() : runPipeline();
      start
        .then(() => navigate(a.kind === 'screener' ? '/screener' : '/runs'))
        .catch((err: Error) => setMessages((prev) => [...prev,
          { role: 'assistant', mode: 'status', local: true,
            content: `Could not start the run: ${err.message}` }]));
    }
  };

  const requestChanges = () => {
    setInput('Request changes to the draft: ');
    inputRef.current?.focus();
  };

  const hasConstitution = !!strategy?.active_version;
  const draftBusy = approve.isPending || reject.isPending;
  const pendingId = strategy ? (strategy.pending_proposal?.id ?? null) : undefined;
  const isDrawer = variant === 'drawer';

  return (
    <>
      <div className="chat-scroll">
        <div className="chat-thread" style={isDrawer ? { maxWidth: '100%' } : undefined}>
          {messages.length === 0 && (
            <div className="chat-bubble chat-bubble-assistant">
              <div className="chat-meta-row">FundOps</div>
              {isDrawer ? (
                <div style={{ color: 'var(--text-secondary)' }}>
                  Ask about the data on this page or anything in your workspace — e.g. “compare
                  this with a peer on ROIC”, “show the 1y price chart”, “what are my holdings”.
                </div>
              ) : hasConstitution ? (
                <div style={{ color: 'var(--text-secondary)' }}>
                  Ask about your strategy, your data, or the archive — e.g. “compare two tickers
                  on ROIC”, “screen for high-margin companies right now”, “why did we pass on a
                  ticker”. Strategy changes always come back as a draft for approval.
                </div>
              ) : (
                <div style={{ color: 'var(--text-secondary)' }}>
                  Describe how you want to invest — style, return hurdles, quality bars, what you
                  avoid. FundOps will draft a Constitution: typed rules with plain-English
                  interpretations. You approve it before anything is wired or run.
                </div>
              )}
            </div>
          )}

          {messages.map((m, i) => {
            const chip = m.role === 'assistant' && m.mode ? MODE_CHIPS[m.mode] : undefined;
            return (
              <div
                key={i}
                className={`chat-bubble ${m.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}
              >
                <div className="chat-meta-row">
                  <span>{m.role === 'user' ? 'You' : 'FundOps'}</span>
                  {chip && <span className={`mode-chip ${chip.className}`}>{chip.label}</span>}
                </div>
                <div
                  className="chat-md"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
                />
                {m.blocks && <ChatBlocks blocks={m.blocks} />}
                {m.draft && (
                  <DraftCard
                    draft={m.draft}
                    activeVersion={strategy?.active_version}
                    pendingId={pendingId}
                    fromHistory={m.fromHistory}
                    resolution={resolutions[m.draft.id]}
                    busy={draftBusy}
                    onApprove={(id) => approve.mutate(id)}
                    onRequestChanges={requestChanges}
                    onCancel={(id) => reject.mutate(id)}
                  />
                )}
                {((m.citations?.length ?? 0) > 0 || (m.actions?.length ?? 0) > 0) && (
                  <div className="pill-row" style={{ marginTop: 8 }}>
                    {m.citations?.map((c, ci) => (
                      <button
                        key={`c${ci}`}
                        className="citation-chip"
                        onClick={() => openCitation(c)}
                        title={c.kind}
                      >
                        <span className="citation-kind">{humanize(c.kind)}</span>
                        {c.label}
                      </button>
                    ))}
                    {m.actions?.map((a, ai) => (
                      <button key={`a${ai}`} className="citation-chip" onClick={() => runAction(a)}>
                        {a.label} →
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {send.isPending && <PendingBubble />}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="chat-input-bar">
        <div className="chat-input-inner" style={isDrawer ? { maxWidth: '100%' } : undefined}>
          <textarea
            ref={inputRef}
            className="chat-textarea"
            rows={1}
            value={input}
            disabled={send.isPending}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              isDrawer
                ? pageContext?.ticker
                  ? `Ask about ${pageContext.ticker}, your portfolio, or run a quick screen…`
                  : 'Ask about your data, portfolio, or run a quick screen…'
                : hasConstitution
                  ? 'Message FundOps — strategy changes come back as drafts for approval'
                  : 'Describe how you want to invest…'
            }
          />
          <button
            className="btn btn-accent"
            disabled={send.isPending || !input.trim()}
            onClick={submit}
          >
            Send
          </button>
        </div>
        {!isDrawer && (
          <div
            style={{
              maxWidth: 720,
              margin: '4px auto 0',
              fontSize: 10,
              fontFamily: 'var(--font-data)',
              color: 'var(--text-muted)',
            }}
          >
            Enter to send · Shift+Enter for a new line
          </div>
        )}
      </div>
    </>
  );
}
