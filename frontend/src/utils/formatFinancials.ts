/**
 * Canonical financial formatting utilities.
 *
 * ALL financial percentages from the backend are 0-1 decimals (0.25 = 25%).
 * Frontend always multiplies by 100 for display. No heuristics, no guessing.
 */

/** Format a 0-1 decimal as a percentage string. Always × 100. */
export function pct(val: number | undefined | null, decimals = 1): string {
  if (val == null || Number.isNaN(val)) return '—';
  const asPercent = val * 100;
  if (Math.abs(asPercent) > 999) return '—'; // data quality issue
  return `${asPercent.toFixed(decimals)}%`;
}

/** Format a 0-1 decimal as a signed percentage (+25.0%, -3.2%). */
export function pctSigned(val: number | undefined | null, decimals = 1): string {
  if (val == null || Number.isNaN(val)) return '—';
  const asPercent = val * 100;
  if (Math.abs(asPercent) > 999) return '—';
  return `${asPercent >= 0 ? '+' : ''}${asPercent.toFixed(decimals)}%`;
}

/** Format a value that is ALREADY a percentage (e.g., expected_return = 22.5 means 22.5%). */
export function fmtPct(val: number | undefined | null, decimals = 1): string {
  if (val == null || Number.isNaN(val)) return '—';
  return `${val >= 0 ? '+' : ''}${Number(val).toFixed(decimals)}%`;
}

/** Format a ratio (e.g., P/E = 25.3x, D/E = 1.2x). */
export function fmtRatio(val: number | undefined | null, decimals = 1): string {
  if (val == null || Number.isNaN(val)) return '—';
  return `${Number(val).toFixed(decimals)}x`;
}

/** Format a multiple (e.g., P/E = 25.3). No suffix. */
export function fmtMultiple(val: number | undefined | null, decimals = 1): string {
  if (val == null || Number.isNaN(val)) return '—';
  return Number(val).toFixed(decimals);
}

/** Format USD amount with K/M/B/T suffix. */
export function fmtBigUsd(val: number | undefined | null): string {
  if (val == null || Number.isNaN(val)) return '—';
  const n = Number(val);
  const a = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  return `${sign}$${a.toFixed(0)}`;
}

/**
 * Canonical field definitions: backend name → display label + format type.
 * Import this when you need to render financial data consistently.
 */
export const FINANCIAL_FIELDS = {
  // Margins (0-1 decimals)
  grossProfitMargin: { label: 'Gross Margin', format: 'pct' },
  operatingMargin: { label: 'Op Margin', format: 'pct' },
  netProfitMargin: { label: 'Net Margin', format: 'pct' },
  ebitdaMargin: { label: 'EBITDA Margin', format: 'pct' },
  fcfMargin: { label: 'FCF Margin', format: 'pct' },

  // Returns (0-1 decimals)
  returnOnEquity: { label: 'ROE', format: 'pct' },
  returnOnInvestedCapital: { label: 'ROIC', format: 'pct' },

  // Growth (0-1 decimals)
  revenueGrowth: { label: 'Rev Growth', format: 'pct' },
  earningsGrowth: { label: 'EPS Growth', format: 'pct' },
  revenueGrowth1y: { label: 'Rev Growth 1Y', format: 'pct' },
  revenueGrowth3y: { label: 'Rev Growth 3Y CAGR', format: 'pct' },
  revenueGrowth5y: { label: 'Rev Growth 5Y CAGR', format: 'pct' },

  // Yields (0-1 decimals)
  earningsYield: { label: 'Earnings Yield', format: 'pct' },
  fcfYield: { label: 'FCF Yield', format: 'pct' },
  impliedGrowth: { label: 'Implied Growth', format: 'pct' },

  // Ratios (raw numbers)
  debtEquity: { label: 'D/E', format: 'ratio' },
  debtToEbitda: { label: 'Debt/EBITDA', format: 'ratio' },
  interestCoverage: { label: 'Int Coverage', format: 'ratio' },
  pe: { label: 'P/E', format: 'multiple' },

  // Quality (raw numbers)
  fcfConversion: { label: 'FCF Conversion', format: 'pct' },
  incomeQuality: { label: 'Income Quality', format: 'ratio' },
} as const;

export type FinancialFieldName = keyof typeof FINANCIAL_FIELDS;

/* ── Workflow rebuild additions ──────────────────────────────────────── */

/** Compact USD for KPI rows: $1.2M / $830.4K / -$12. */
export function fmtUsdCompact(val: number | undefined | null): string {
  if (val == null || Number.isNaN(val)) return '—';
  const n = Number(val);
  const a = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

/** Signed compact USD for P&L: +$1.2K / -$340. */
export function fmtPnl(val: number | undefined | null): string {
  if (val == null || Number.isNaN(val)) return '—';
  return `${Number(val) >= 0 ? '+' : ''}${fmtUsdCompact(val)}`;
}

/** Plain price: $182.34 */
export function fmtPrice(val: number | undefined | null): string {
  if (val == null || Number.isNaN(val)) return '—';
  return `$${Number(val).toFixed(2)}`;
}

/**
 * Parse a backend timestamp without timezone surprises. Date-only strings
 * (YYYY-MM-DD — ledger dates, filing dates, as-of dates) are calendar dates:
 * `new Date('2026-06-12')` would parse as UTC midnight and display as the
 * previous day anywhere west of UTC, so they're constructed as local dates.
 */
export function parseDate(iso: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(iso);
}

/** Short date: Mar 4, 2026. Falls back to the raw string when unparseable. */
export function fmtDate(iso: string | undefined | null): string {
  if (!iso) return '—';
  const d = parseDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

/** Today as a YYYY-MM-DD string in the user's local calendar (form defaults). */
export function localToday(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Shares / integer counts with thousands separators. */
export function fmtShares(val: number | undefined | null): string {
  if (val == null || Number.isNaN(val)) return '—';
  return Number(val).toLocaleString();
}

/** snake_case / camelCase → Title Case label. */
export function humanizeLabel(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Heuristic formatter for arbitrary backend metric keys (screener key
 * financials, company financial statements). Strings pass through as-is.
 */
export function fmtMetric(metric: string, value: number | string | null | undefined): string {
  if (value == null || (typeof value === 'number' && Number.isNaN(value))) return '—';
  if (typeof value === 'string') return value;
  const m = metric.toLowerCase();
  if (m.includes('market_cap') || m.includes('marketcap')) return fmtBigUsd(value);
  if (m.includes('dollar_volume')) return fmtBigUsd(value);
  if (/momentum|below_52w|drawdown/.test(m)) return pctSigned(value);
  if (/(margin|growth|yield|roic|roe|roa|payout|conversion|volatility)/.test(m)) return pct(value);
  if (/(^|_)volume/.test(m)) return Number(value).toLocaleString();
  if (/(debt_equity|debtequity|debt_to|coverage|current_ratio|quick_ratio|turnover|quality)/.test(m)) return fmtRatio(value);
  if (/(^|_)pe($|_)|price_to|ev_to|multiple/.test(m)) return fmtMultiple(value);
  if (/price|cost|revenue|income|profit|assets|liabilit|equity|cash|debt|capex|fcf|flow|expenditure|dividend/.test(m)) {
    return Math.abs(value) >= 1e5 ? fmtBigUsd(value) : `$${value.toFixed(2)}`;
  }
  if (/eps/.test(m)) return `$${value.toFixed(2)}`;
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

/** Auto-format a financial field value based on its canonical definition. */
export function fmtField(fieldName: string, val: number | undefined | null): string {
  const def = FINANCIAL_FIELDS[fieldName as FinancialFieldName];
  if (!def) return val == null ? '—' : String(val);
  switch (def.format) {
    case 'pct': return pct(val);
    case 'ratio': return fmtRatio(val);
    case 'multiple': return fmtMultiple(val);
    default: return val == null ? '—' : String(val);
  }
}
