/**
 * Shared display helpers for typed strategy criteria — used by the draft card
 * in the chat thread and the capability wiring panel on the Chat page.
 */

import type { CriterionRule } from '../../api/client';
import { fmtMetric, humanizeLabel } from '../../utils/formatFinancials';

export const OPERATOR_SYMBOLS: Record<string, string> = {
  '>=': '≥',
  '<=': '≤',
  '>': '>',
  '<': '<',
  '==': '=',
  '=': '=',
};

export type SettingsRecord = Record<string, unknown>;

export function isRecord(x: unknown): x is SettingsRecord {
  return !!x && typeof x === 'object' && !Array.isArray(x);
}

export function isCriterionLike(x: unknown): x is CriterionRule & SettingsRecord {
  if (!isRecord(x)) return false;
  return (
    typeof x.criterion_id === 'string' ||
    (typeof x.kind === 'string' && ('metric' in x || 'operator' in x || 'rule' in x))
  );
}

export function humanize(key: string | null | undefined): string {
  if (!key) return '—';
  return key.replace(/_/g, ' ');
}

/** Bold rule line: prefer a backend-provided `rule`; else compose from parts. */
export function criterionRuleLine(c: CriterionRule & SettingsRecord): string {
  if (typeof c.rule === 'string' && c.rule) return c.rule;
  const name = humanizeLabel(
    c.metric ?? (c.criterion_id ? c.criterion_id.split('.').pop() ?? c.criterion_id : c.kind),
  );
  if (c.kind === 'rank') return `Rank by ${name}`;
  const parts: string[] = [name];
  if (c.operator) parts.push(OPERATOR_SYMBOLS[c.operator] ?? c.operator);
  if (c.value !== undefined && c.value !== null && typeof c.value !== 'object') {
    parts.push(
      typeof c.value === 'number' ? fmtMetric(c.metric ?? '', c.value) : String(c.value),
    );
  }
  return parts.join(' ');
}
