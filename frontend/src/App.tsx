import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Link, Navigate } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { ChatDrawer } from './components/chat/ChatDrawer';
import { AskPopover } from './components/AskAnywhere';
import { CommandPalette } from './components/CommandPalette';
import { WiringOverlay } from './components/WiringOverlay';
import { ToastProvider } from './components/Toast';
import Home from './pages/Home';
import Dashboard from './pages/Dashboard';
import Runs from './pages/Runs';
import Settings from './pages/Settings';
import Screener from './pages/Screener';
import Thesis from './pages/Thesis';
import ICReview from './pages/ICReview';
import Memo from './pages/Memo';
import Portfolio from './pages/Portfolio';
import Library from './pages/Library';
import Research from './pages/Research';
import CompanyPage from './pages/CompanyPage';
import ArtifactReader from './pages/ArtifactReader';

function NotFound() {
  return (
    <div style={{ padding: '80px 24px', textAlign: 'center' }}>
      <div
        style={{
          fontFamily: 'var(--font-data)',
          fontSize: 'var(--text-xl)',
          color: 'var(--text-muted)',
          marginBottom: 8,
        }}
      >
        404
      </div>
      <div
        style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--text-secondary)',
          marginBottom: 16,
        }}
      >
        This page does not exist.
      </div>
      <Link to="/" style={{ color: 'var(--teal-ink)', fontSize: 'var(--text-sm)' }}>
        Go Home
      </Link>
    </div>
  );
}

export default function App() {
  const [wiringOpen, setWiringOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === 'Escape') {
        setPaletteOpen(false);
        setWiringOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <BrowserRouter>
      <ToastProvider>
      <div className="page-shell">
        <Sidebar onOpenWiring={() => setWiringOpen(true)} onOpenPalette={() => setPaletteOpen(true)} />
        <div className="page-content">
          <main className="page-main">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/inbox" element={<Dashboard />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/markets" element={<Research />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/library" element={<Library />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/company/:ticker" element={<CompanyPage />} />
              <Route path="/artifact/:id" element={<ArtifactReader />} />
              {/* stage workbenches — reached from Runs */}
              <Route path="/screener" element={<Screener />} />
              <Route path="/thesis" element={<Thesis />} />
              <Route path="/ic-review" element={<ICReview />} />
              <Route path="/memo" element={<Memo />} />
              {/* legacy paths */}
              <Route path="/dashboard" element={<Navigate to="/inbox" replace />} />
              <Route path="/research" element={<Navigate to="/markets" replace />} />
              <Route path="/chat" element={<Navigate to="/" replace />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
        </div>
        <ChatDrawer />
        <AskPopover />
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        {wiringOpen && <WiringOverlay onClose={() => setWiringOpen(false)} />}
      </div>
      </ToastProvider>
    </BrowserRouter>
  );
}
