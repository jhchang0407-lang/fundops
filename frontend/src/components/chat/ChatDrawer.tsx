/**
 * The companion: one conversation, two homes. On Home the thread is the
 * page; everywhere else this panel summons the SAME thread (shared module
 * state + session) docked to the right, carrying the page's context.
 * Point-at-anything popovers open it automatically before sending.
 */

import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChatThread } from './ChatThread';
import type { ChatPageContext } from '../../api/client';

function contextForPath(pathname: string): ChatPageContext | null {
  const company = pathname.match(/^\/company\/([^/]+)/);
  if (company) return { page: 'company', ticker: decodeURIComponent(company[1]).toUpperCase() };
  if (pathname.startsWith('/portfolio')) return { page: 'portfolio' };
  if (pathname.startsWith('/markets')) return { page: 'markets' };
  if (pathname.startsWith('/screener')) return { page: 'screener' };
  if (pathname.startsWith('/inbox')) return { page: 'inbox' };
  if (pathname.startsWith('/runs')) return { page: 'runs' };
  if (pathname.startsWith('/thesis')) return { page: 'thesis' };
  if (pathname.startsWith('/ic-review')) return { page: 'ic_review' };
  if (pathname.startsWith('/memo')) return { page: 'memo' };
  if (pathname.startsWith('/library')) return { page: 'library' };
  const artifact = pathname.match(/^\/artifact\/([^/]+)/);
  if (artifact) return { page: 'artifact', artifact_id: decodeURIComponent(artifact[1]) };
  return null;
}

export function ChatDrawer() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const context = useMemo(() => contextForPath(pathname), [pathname]);
  const onHome = pathname === '/';

  // Popovers and other surfaces summon the companion via this event.
  useEffect(() => {
    const onSummon = () => { if (!onHome) setOpen(true); };
    window.addEventListener('fundops:companion', onSummon);
    return () => window.removeEventListener('fundops:companion', onSummon);
  }, [onHome]);

  // The thread lives inline on Home — close the companion when arriving there.
  useEffect(() => {
    if (onHome) setOpen(false);
  }, [onHome]);

  // Push the app content over while open.
  useEffect(() => {
    document.body.classList.toggle('companion-open', open && !onHome);
    return () => document.body.classList.remove('companion-open');
  }, [open, onHome]);

  if (onHome) return null;

  return (
    <>
      {!open && (
        <button
          className="companion-spark"
          onClick={() => setOpen(true)}
          aria-label="Open conversation panel"
          title="The conversation follows you — same thread as Home"
        >
          <span style={{ color: 'var(--teal)' }}>✦</span> Conversation
        </button>
      )}
      {open && (
        <aside className="companion">
          <div className="companion-head">
            <span style={{ color: 'var(--teal)' }}>✦</span>
            <b style={{ fontSize: 'var(--text-sm)' }}>Conversation</b>
            {context && (
              <span className="chat-context-chip">
                Viewing: {context.ticker ?? context.page.replace(/_/g, ' ')}
              </span>
            )}
            <button
              className="reader-popup-close"
              style={{ marginLeft: 'auto' }}
              title="Open full at Home"
              onClick={() => { setOpen(false); navigate('/'); }}
            >
              ⤢
            </button>
            <button className="reader-popup-close" onClick={() => setOpen(false)}>
              ✕
            </button>
          </div>
          <div className="companion-hint">
            Same thread as Home — it follows you. Click any number or row to ask about it.
          </div>
          <div className="companion-body">
            <ChatThread variant="drawer" pageContext={context} />
          </div>
        </aside>
      )}
    </>
  );
}
