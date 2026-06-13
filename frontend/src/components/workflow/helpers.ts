/**
 * Non-component helpers shared by the workflow stage components/pages.
 * (Separate file so component modules stay fast-refresh friendly.)
 */
import { humanizeLabel } from '../../utils/formatFinancials';

/* Safe accessors for optional growth fields — the API contract allows
   response field lists to grow without changing meaning. */
export function extraStr(o: object, key: string): string | null {
  const v = (o as Record<string, unknown>)[key];
  return typeof v === 'string' && v.length > 0 ? v : null;
}

export function extraNum(o: object, key: string): number | null {
  const v = (o as Record<string, unknown>)[key];
  return typeof v === 'number' && !Number.isNaN(v) ? v : null;
}

export interface ReturnComponentEntry {
  label: string;
  value: number;
}

/** Accept either `{label → pct}` records or `[{label|name, value|pct}]` arrays. */
export function normalizeReturnComponents(raw: unknown): ReturnComponentEntry[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    const out: ReturnComponentEntry[] = [];
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue;
      const o = item as Record<string, unknown>;
      const label =
        typeof o.label === 'string'
          ? o.label
          : typeof o.name === 'string'
            ? o.name
            : typeof o.component === 'string'
              ? o.component
              : null;
      const value = typeof o.value === 'number' ? o.value : typeof o.pct === 'number' ? o.pct : null;
      if (label && value != null) out.push({ label: humanizeLabel(label), value });
    }
    return out;
  }
  if (typeof raw === 'object') {
    return Object.entries(raw as Record<string, unknown>)
      .filter((e): e is [string, number] => typeof e[1] === 'number')
      .map(([k, v]) => ({ label: humanizeLabel(k), value: v }));
  }
  return [];
}
