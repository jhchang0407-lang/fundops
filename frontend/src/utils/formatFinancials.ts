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
  if (val == null) return '—';
  const n = Number(val);
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(0)}`;
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
