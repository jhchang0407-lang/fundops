import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './components/Sidebar';
import { JobTracker } from './components/JobTracker';
import { Mirror } from './pages/Mirror';
import { Dashboard } from './pages/Dashboard';
import Configure from './pages/Configure';
import { Screener } from './pages/Screener';
import Research from './pages/Research';
import { Library } from './pages/Library';
import { Portfolio } from './pages/Portfolio';
import { Allocator } from './pages/Allocator';
import { TickerDetail } from './pages/TickerDetail';
import { Settings } from './pages/Settings';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="page-shell">
          <Sidebar />
          <div className="page-content">
          <JobTracker />
          <main className="page-main">
            <Routes>
              <Route path="/" element={<Configure />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/mirror" element={<Mirror />} />
              <Route path="/screener" element={<Screener />} />
              <Route path="/research" element={<Research />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/library" element={<Library />} />
              <Route path="/allocator" element={<Allocator />} />
              <Route path="/ticker/:ticker" element={<TickerDetail />} />
              <Route path="/settings" element={<Settings />} />
              {/* Redirects */}
              <Route path="/thesis" element={<Navigate to="/research" replace />} />
              <Route path="/ic-review" element={<Navigate to="/research" replace />} />
              {/* /dashboard redirect removed — now a real route above */}
              <Route path="/memo" element={<Navigate to="/research" replace />} />
              <Route path="/memo/:ticker" element={<Navigate to="/research" replace />} />
              <Route path="*" element={
                <div style={{ padding: '60px 24px', textAlign: 'center' }}>
                  <div style={{ fontSize: 48, fontFamily: 'var(--font-data)', color: 'var(--accent)', marginBottom: 12 }}>404</div>
                  <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 24 }}>Page not found</div>
                  <a href="/dashboard" style={{ color: 'var(--accent)', fontSize: 13 }}>Go to Dashboard</a>
                </div>
              } />
            </Routes>
          </main>
          </div>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
