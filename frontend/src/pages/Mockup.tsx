import { useMemo, useState } from 'react';

type ViewKey = 'mirror' | 'research' | 'ticker' | 'library';

const views: Array<{ key: ViewKey; label: string; subtitle: string }> = [
  { key: 'mirror', label: 'Home / Mirror', subtitle: 'Constitution, drift, actions, and learning' },
  { key: 'research', label: 'Research', subtitle: 'Thesis and IC workbench' },
  { key: 'ticker', label: 'Ticker Detail', subtitle: 'Single-name decision workspace' },
  { key: 'library', label: 'Library', subtitle: 'Institutional memory and prior work' },
];

function MockupHeader({
  kicker,
  title,
  subtitle,
}: {
  kicker: string;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="stack" style={{ gap: 4 }}>
      <div className="page-kicker">{kicker}</div>
      <h1 className="page-title">{title}</h1>
      <div className="page-subtitle">{subtitle}</div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: 'default' | 'positive' | 'negative' | 'accent';
}) {
  const color =
    tone === 'positive'
      ? 'var(--positive)'
      : tone === 'negative'
        ? 'var(--negative)'
        : tone === 'accent'
          ? 'var(--accent)'
          : 'var(--text-primary)';

  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color }}>{value}</div>
      {detail && <div className="kpi-detail">{detail}</div>}
    </div>
  );
}

function SignalPill({ text, kind }: { text: string; kind: 'positive' | 'negative' | 'muted' }) {
  return <span className={`pill pill-${kind}`}>{text}</span>;
}

function MockupShell({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="card glass-card" style={{ padding: 18 }}>
      <div className="page-header" style={{ marginBottom: 18 }}>
        <MockupHeader kicker="Preview" title={title} subtitle={subtitle} />
        {right}
      </div>
      {children}
    </div>
  );
}

function MirrorMockup() {
  return (
    <MockupShell
      title="The Mirror"
      subtitle="Your investment constitution, revealed behavior, and system learning in one operating surface."
      right={<button className="btn btn-accent">Refine Constitution</button>}
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="card" style={{ marginBottom: 0, background: 'rgba(255,255,255,0.015)' }}>
          <div className="two-col" style={{ alignItems: 'start' }}>
            <div className="stack" style={{ gap: 10 }}>
              <div className="card-title">Constitution Snapshot</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.55rem', lineHeight: 1.2, maxWidth: 760 }}>
                “Buy durable compounders when the market is underwriting transitory pressure and the path to rerating is intelligible.”
              </div>
              <div style={{ color: 'var(--text-secondary)', maxWidth: 760 }}>
                Concentrated quality-at-a-discount investor. Prefers businesses with high incremental returns, durable free cash flow,
                clear owner-operator alignment, and enough dislocation for a multi-year rerating without underwriting heroic assumptions.
              </div>
              <div className="inline-metadata">
                <span>Style: Concentrated value + compounder</span>
                <span>Horizon: 3-5 years</span>
                <span>Version 4</span>
                <span>Updated March 29</span>
              </div>
            </div>
            <div className="stack" style={{ minWidth: 210 }}>
              <div className="banner banner-warning">
                Behavioral calibration is active. Recent approvals are drifting slightly more cyclical than your stated style.
              </div>
            </div>
          </div>

          <div className="three-col" style={{ marginTop: 18 }}>
            <div className="stack">
              <div className="card-title">Must-Have Signals</div>
              <div className="pill-row">
                <SignalPill kind="positive" text="High ROIC durability" />
                <SignalPill kind="positive" text="FCF resilience" />
                <SignalPill kind="positive" text="Capital allocator you trust" />
                <SignalPill kind="positive" text="Variant view from sentiment reset" />
              </div>
            </div>
            <div className="stack">
              <div className="card-title">Anti-Signals</div>
              <div className="pill-row">
                <SignalPill kind="negative" text="Leverage creep" />
                <SignalPill kind="negative" text="Narrative-only upside" />
                <SignalPill kind="negative" text="Turnaround disguised as quality" />
              </div>
            </div>
            <div className="stack">
              <div className="card-title">IC Hurdles</div>
              <div className="inline-metadata" style={{ gap: 12 }}>
                <span>Base 20%</span>
                <span>Bear 15%</span>
                <span>Haircut 70%</span>
                <span>Max pos 12%</span>
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                The system stress-tests every thesis against your downside discipline before memo spend.
              </div>
            </div>
          </div>
        </div>

        <div className="two-col">
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Said vs Did</div>
            <div className="stack">
              <div className="banner banner-warning">
                You say you want stable compounders, but 3 of your last 8 approvals leaned cyclical rerating.
              </div>
              <div className="table-shell" style={{ border: 'none', borderRadius: 0 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Signal</th>
                      <th className="num">Violation</th>
                      <th>Affected</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Revenue durability</td>
                      <td className="num" style={{ color: 'var(--warning)' }}>22%</td>
                      <td>3 approvals</td>
                    </tr>
                    <tr>
                      <td>Low leverage preference</td>
                      <td className="num" style={{ color: 'var(--negative)' }}>31%</td>
                      <td>PAYC, UMAC, RCAT</td>
                    </tr>
                    <tr>
                      <td>Management quality</td>
                      <td className="num">8%</td>
                      <td>1 approval</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="three-col" style={{ gap: 10 }}>
                <MetricCard label="IC Pass Rate" value="44%" detail="8 pass / 18 reviewed" />
                <MetricCard label="Conviction Median" value="4/5" detail="Skews high once passed" />
                <MetricCard label="Style Drift" value="Moderate" detail="Mostly cyclical bias" tone="accent" />
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Portfolio + Actions</div>
            <div className="kpi-grid">
              <MetricCard label="Portfolio Value" value="$759K" detail="+$94K total P&L" />
              <MetricCard label="Daily P&L" value="+$6.8K" detail="+0.9% today" tone="positive" />
              <MetricCard label="Positions" value="14" detail="9 core / 3 tactical / 2 legacy" />
              <MetricCard label="Alerts" value="3" detail="1 concentration, 2 thesis drift" tone="negative" />
            </div>
            <div className="stack" style={{ marginTop: 14 }}>
              <div className="banner banner-warning">
                TRIM RCAT from 17.4% to 11.0%. Concentration drift exceeds your optionality rules.
              </div>
              <div className="banner">
                REUNDERWRITE UMAC. Thesis health fell to 22/100 after margin deterioration.
              </div>
              <div className="banner banner-positive">
                ADD ON WEAKNESS for CHKP. Weight below target despite thesis health holding at 82/100.
              </div>
            </div>
          </div>
        </div>

        <div className="two-col">
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Your Attention</div>
            <div className="stack">
              <div style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span className="ticker">GOOGL</span>
                  <span className="badge badge-pass">IC PASS</span>
                </div>
                <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                  Fits your constitution because the market is pricing a maturing platform while FCF durability, capital discipline,
                  and optionality remain intact.
                </div>
                <div className="inline-metadata" style={{ marginTop: 8 }}>
                  <span>Expected return 28%</span>
                  <span>Constitution fit 91</span>
                  <span>Next: memo</span>
                </div>
              </div>

              <div style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span className="ticker">META</span>
                  <span className="badge badge-running">Health Change</span>
                </div>
                <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                  Thesis intact, but sentiment rerating is happening faster than fundamental confirmation. Watch expectation risk.
                </div>
              </div>

              <div style={{ paddingBottom: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span className="ticker">PAYC</span>
                  <span className="badge badge-muted">Needs Recheck</span>
                </div>
                <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                  Similar to two prior approved compounders, but with weaker customer durability than your usual yes-pattern.
                </div>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">System Learning</div>
            <div className="stack">
              <div className="banner">
                Proposal: add a modest penalty for deteriorating margin profile in screens. Confidence 78%. Based on 4 dismissals and 2 failed theses.
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-accent">Accept</button>
                <button className="btn">Reject</button>
              </div>
              <div style={{ paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                <div className="section-kicker" style={{ marginBottom: 10 }}>Recent Learning Log</div>
                <div className="stack" style={{ gap: 8 }}>
                  <div className="inline-metadata">
                    <span>Mar 29</span>
                    <span>Screener dismiss pattern detected in margin-degrading software names</span>
                  </div>
                  <div className="inline-metadata">
                    <span>Mar 28</span>
                    <span>Counterfactual watch started on AMZN NO_PASS</span>
                  </div>
                  <div className="inline-metadata">
                    <span>Mar 26</span>
                    <span>Allocator override recorded: user kept RCAT above model weight</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </MockupShell>
  );
}

function ResearchMockup() {
  return (
    <MockupShell
      title="Research Workbench"
      subtitle="Where screened names become judgment-ready decisions."
      right={<button className="btn btn-accent">Run Batch IC Review</button>}
    >
      <div className="stack">
        <div className="pill-row">
          <SignalPill kind="muted" text="All" />
          <SignalPill kind="positive" text="IC Passed" />
          <SignalPill kind="negative" text="IC Failed" />
          <SignalPill kind="muted" text="Pending IC" />
        </div>

        <div className="card" style={{ marginBottom: 0, padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '120px 100px 100px 120px 120px 1fr 140px', gap: 12, alignItems: 'center' }}>
              <div className="section-kicker">Ticker</div>
              <div className="section-kicker">Expected</div>
              <div className="section-kicker">Discount</div>
              <div className="section-kicker">IC Verdict</div>
              <div className="section-kicker">Constitution Fit</div>
              <div className="section-kicker">Thesis Read</div>
              <div className="section-kicker">Next</div>
            </div>
          </div>

          <div style={{ padding: 16, borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.015)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '120px 100px 100px 120px 120px 1fr 140px', gap: 12, alignItems: 'center' }}>
              <div>
                <div className="ticker">GOOGL</div>
                <div className="muted" style={{ marginTop: 4 }}>Alphabet</div>
              </div>
              <div className="pos">28%</div>
              <div>35%</div>
              <div><span className="badge badge-pass">PASS</span></div>
              <div>91</div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Quality platform misread as ex-growth while owner earnings and capital discipline remain unusually resilient.
              </div>
              <div><button className="btn btn-accent">Generate Memo</button></div>
            </div>

            <div className="two-col" style={{ marginTop: 18 }}>
              <div className="stack">
                <div className="card-title">Constitution Scorecard</div>
                <div className="inline-metadata">
                  <span>Cheapness: pass</span>
                  <span>FCF quality: pass</span>
                  <span>Leverage discipline: pass</span>
                  <span>Narrative risk: pass</span>
                </div>

                <div className="card-title" style={{ marginTop: 8 }}>Key Assumptions</div>
                <div style={{ color: 'var(--text-secondary)' }}>
                  Search monetization remains structurally healthy, capex intensity yields platform leverage, and AI monetization does not require heroic adoption timing.
                </div>
              </div>

              <div className="stack">
                <div className="card-title">Similar Names From Library</div>
                <div className="banner banner-positive">
                  Similar to MSFT in 2024: approved, thesis intact, +40% since memo.
                </div>
                <div className="banner">
                  Similar to ADBE in 2025: approved, but rerating lagged because sentiment stayed compressed longer than expected.
                </div>
              </div>
            </div>
          </div>

          <div style={{ padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '120px 100px 100px 120px 120px 1fr 140px', gap: 12, alignItems: 'center' }}>
              <div>
                <div className="ticker">AMZN</div>
                <div className="muted" style={{ marginTop: 4 }}>Amazon</div>
              </div>
              <div className="pos">22%</div>
              <div>18%</div>
              <div><span className="badge badge-running">Pending IC</span></div>
              <div>84</div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Owner-earnings quality fits, but the constitution fit is slightly weaker because rerating depends more on execution confidence than your usual yeses.
              </div>
              <div><button className="btn">Run IC Review</button></div>
            </div>
          </div>
        </div>
      </div>
    </MockupShell>
  );
}

function TickerMockup() {
  return (
    <MockupShell
      title="Ticker Detail"
      subtitle="Everything the system knows about one company, in a single-name decision workspace."
      right={
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn">Run Thesis</button>
          <button className="btn btn-accent">Open Memo</button>
        </div>
      }
    >
      <div className="stack">
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-title">Judgment Chain</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {['SCREENED', 'PROMOTED', 'THESIS', 'IC PASS', 'MEMO', 'OUTCOME'].map((step, index) => (
              <div
                key={step}
                style={{
                  minWidth: 120,
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: `1px solid ${index < 4 ? 'rgba(245,166,35,0.24)' : 'var(--border)'}`,
                  background: index < 4 ? 'rgba(245,166,35,0.06)' : 'transparent',
                }}
              >
                <div className="section-kicker">{step}</div>
                <div style={{ marginTop: 8, color: index < 4 ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {index < 4 ? 'Captured' : 'Pending'}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="two-col">
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Thesis</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem' }}>GOOGL</div>
            <div className="inline-metadata" style={{ marginTop: 8 }}>
              <span>Expected return 28%</span>
              <span>Discount 35%</span>
              <span>Fair value $220</span>
            </div>
            <div style={{ marginTop: 12, color: 'var(--text-secondary)' }}>
              The market is underwriting maturing search economics while underestimating the durability of owner earnings and the breadth of monetization optionality.
            </div>
          </div>

          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">IC Review</div>
            <div><span className="badge badge-pass">PASS</span></div>
            <div className="inline-metadata" style={{ marginTop: 10 }}>
              <span>Base 28%</span>
              <span>Bear 17%</span>
              <span>Conviction 4/5</span>
            </div>
            <div style={{ marginTop: 12, color: 'var(--text-secondary)' }}>
              Biggest risk: capital intensity and expectation inflation create a narrower path than the headline multiple suggests.
            </div>
          </div>
        </div>

        <div className="two-col">
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Judgment Event Timeline</div>
            <div className="stack">
              <div className="inline-metadata">
                <span>Mar 28</span>
                <span>Screened #1 in compounder lens</span>
              </div>
              <div className="inline-metadata">
                <span>Mar 28</span>
                <span>Promoted to thesis by user</span>
              </div>
              <div className="inline-metadata">
                <span>Mar 29</span>
                <span>IC PASS at 4/5 conviction</span>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Related Library Context</div>
            <div className="stack">
              <div className="banner banner-positive">
                Similar to MSFT, approved 18 months ago, thesis still intact.
              </div>
              <div className="banner">
                Similar to ADBE, where sentiment stayed compressed longer than expected.
              </div>
            </div>
          </div>
        </div>
      </div>
    </MockupShell>
  );
}

function LibraryMockup() {
  return (
    <MockupShell
      title="Research Library"
      subtitle="Institutional memory, prior judgment, and full artifact retrieval."
    >
      <div className="stack">
        <div className="card" style={{ marginBottom: 0 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input
              className="field"
              value="quality compounders we approved in software"
              readOnly
              style={{ flex: 1 }}
            />
            <button className="btn btn-accent">Search</button>
          </div>
          <div className="pill-row" style={{ marginTop: 12 }}>
            <SignalPill kind="muted" text="All" />
            <SignalPill kind="muted" text="Thesis" />
            <SignalPill kind="muted" text="IC" />
            <SignalPill kind="positive" text="PASS only" />
            <SignalPill kind="muted" text="With outcomes" />
          </div>
        </div>

        <div className="two-col">
          <div className="card" style={{ marginBottom: 0, padding: 0 }}>
            <div style={{ padding: 14, borderBottom: '1px solid var(--border)' }}>
              <div className="card-title" style={{ marginBottom: 0 }}>Results</div>
            </div>
            {[
              { ticker: 'GOOGL', type: 'Investment Memo', verdict: 'PASS', fv: '$220', date: '2026-03-28' },
              { ticker: 'MSFT', type: 'Research Memo', verdict: 'PASS', fv: '$470', date: '2025-10-02' },
              { ticker: 'ADBE', type: 'Thesis', verdict: 'NO_PASS', fv: '$610', date: '2025-07-14' },
            ].map((row) => (
              <div key={row.ticker} style={{ padding: 14, borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <div className="ticker">{row.ticker}</div>
                    <div className="muted" style={{ marginTop: 4 }}>{row.type}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className={`badge ${row.verdict === 'PASS' ? 'badge-pass' : 'badge-nopass'}`}>{row.verdict}</span>
                    <div className="muted" style={{ marginTop: 4 }}>{row.date}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="card" style={{ marginBottom: 0 }}>
            <div className="card-title">Preview</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem' }}>GOOGL</div>
            <div className="inline-metadata" style={{ marginTop: 8 }}>
              <span>Investment Memo</span>
              <span>PASS</span>
              <span>FV $220</span>
            </div>
            <div style={{ marginTop: 12, color: 'var(--text-secondary)' }}>
              Approved as a high-quality platform mispriced on sentiment reset. Return path was driven by owner earnings durability and rerating optionality rather than aggressive margin assumptions.
            </div>
            <div className="three-col" style={{ marginTop: 16 }}>
              <MetricCard label="Since Memo" value="+19%" tone="positive" />
              <MetricCard label="Alpha vs SPY" value="+8%" tone="positive" />
              <MetricCard label="Thesis Integrity" value="82" detail="4/5 assumptions intact" />
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-accent">Read Memo</button>
              <button className="btn">Open Ticker</button>
            </div>
          </div>
        </div>
      </div>
    </MockupShell>
  );
}

export function Mockup() {
  const [active, setActive] = useState<ViewKey>('mirror');

  const current = useMemo(() => views.find((view) => view.key === active)!, [active]);

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <div className="page-kicker">Mockup</div>
          <h1 className="page-title">High-Fidelity Product Preview</h1>
          <div className="page-subtitle">
            A realistic concept pass so we can align on feel, hierarchy, and product direction before full implementation.
          </div>
        </div>
      </div>

      <div className="card">
        <div className="pill-row">
          {views.map((view) => (
            <button
              key={view.key}
              className={`btn ${active === view.key ? 'btn-accent' : ''}`}
              onClick={() => setActive(view.key)}
            >
              {view.label}
            </button>
          ))}
        </div>
        <div className="page-subtitle" style={{ marginTop: 12 }}>
          {current.subtitle}
        </div>
      </div>

      {active === 'mirror' && <MirrorMockup />}
      {active === 'research' && <ResearchMockup />}
      {active === 'ticker' && <TickerMockup />}
      {active === 'library' && <LibraryMockup />}
    </div>
  );
}
