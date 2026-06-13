/**
 * Constitution wiring overlay — read-only view of how the active
 * Constitution wires each capability. Opened from the rail's Constitution
 * chip. Strategy changes happen in conversation, never here.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStrategy, getWiring } from '../api/client';
import type { CriterionRule } from '../api/client';
import { fmtMetric, humanizeLabel } from '../utils/formatFinancials';
import {
  criterionRuleLine,
  humanize,
  isCriterionLike,
  isRecord,
} from './chat/criterionDisplay';
import type { SettingsRecord } from './chat/criterionDisplay';

export const CAPABILITIES: { key: string; label: string }[] = [
  { key: 'screener', label: 'Screener' },
  { key: 'thesis', label: 'Thesis' },
  { key: 'ic_review', label: 'IC review' },
  { key: 'memo', label: 'Memo' },
  { key: 'portfolio_review', label: 'Portfolio review' },
  { key: 'universe', label: 'Universe' },
];

function criterionWeight(c: SettingsRecord): string | null {
  const nw = c.normalized_weight ?? c.weight;
  if (typeof nw !== 'number' || Number.isNaN(nw)) return null;
  return `weight ${Math.round((nw <= 1 ? nw * 100 : nw) * 10) / 10}%`;
}

function CriterionRows({ rules }: { rules: (CriterionRule & SettingsRecord)[] }) {
  return (
    <div>
      {rules.map((c, i) => {
        const weight = criterionWeight(c);
        const sub = c.interpretation ?? c.rule_rationale ?? null;
        return (
          <div className="wiring-rule-row" key={c.criterion_id ?? i}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="wiring-rule-main">
                {criterionRuleLine(c)}
                {c.data_support_level && c.data_support_level !== 'fully' && (
                  <span className="locked-tag" style={{ marginLeft: 8 }}>
                    {humanize(c.data_support_level)}
                  </span>
                )}
              </div>
              {sub && <div className="wiring-rule-sub">{sub}</div>}
            </div>
            {weight && <span className="wiring-rule-weight">{weight}</span>}
          </div>
        );
      })}
    </div>
  );
}

function blendLine(record: SettingsRecord): string {
  return Object.entries(record)
    .filter((e): e is [string, number] => typeof e[1] === 'number')
    .map(([k, v]) => `${Math.round((v <= 1 ? v * 100 : v) * 10) / 10}% ${humanize(k)}`)
    .join(' · ');
}

function universeLine(record: SettingsRecord): string {
  const name = typeof record.name === 'string' && record.name ? record.name : 'Universe';
  const count = Array.isArray(record.tickers)
    ? record.tickers.length
    : typeof record.tickers_count === 'number'
      ? record.tickers_count
      : typeof record.count === 'number'
        ? record.count
        : null;
  return count != null ? `${name} (${count} tickers)` : name;
}

function settingValueText(key: string, v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return fmtMetric(key, v);
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'string') return v;
  return '—';
}

function ScalarRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="wiring-kv-row">
      <span className="wiring-kv-key">{label}</span>
      <span className="wiring-kv-val">{value}</span>
    </div>
  );
}

function ChipRow({ items }: { items: string[] }) {
  return (
    <div className="wiring-chip-row">
      {items.map((item, i) => (
        <span className="wiring-chip" key={`${item}-${i}`}>
          {humanizeLabel(item)}
        </span>
      ))}
    </div>
  );
}

function GenericRecordRows({ record, depth = 0 }: { record: SettingsRecord; depth?: number }) {
  return (
    <div style={depth > 0 ? { paddingLeft: 12 } : undefined}>
      {Object.entries(record).map(([k, v]) => {
        if (v === null || v === undefined) return null;
        if (isRecord(v) && depth === 0) {
          return (
            <div key={k} style={{ padding: '4px 0' }}>
              <div className="wiring-kv-key" style={{ marginBottom: 2 }}>
                {humanizeLabel(k)}
              </div>
              <GenericRecordRows record={v} depth={1} />
            </div>
          );
        }
        if (Array.isArray(v)) {
          const strs = v.filter((x): x is string => typeof x === 'string');
          if (strs.length === v.length && strs.length > 0) {
            return (
              <div key={k} style={{ padding: '4px 0' }}>
                <div className="wiring-kv-key" style={{ marginBottom: 4 }}>
                  {humanizeLabel(k)}
                </div>
                <ChipRow items={strs} />
              </div>
            );
          }
          return <ScalarRow key={k} label={humanizeLabel(k)} value={`${v.length} entries`} />;
        }
        if (isRecord(v)) {
          const line = Object.entries(v)
            .filter(([, x]) => x !== null && typeof x !== 'object')
            .map(([kk, x]) => `${humanize(kk)}: ${settingValueText(kk, x)}`)
            .join(' · ');
          return <ScalarRow key={k} label={humanizeLabel(k)} value={line || '—'} />;
        }
        return <ScalarRow key={k} label={humanizeLabel(k)} value={settingValueText(k, v)} />;
      })}
    </div>
  );
}

function WiringSetting({ name, value }: { name: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value) && value.length === 0) return null;
  if (isRecord(value) && Object.keys(value).length === 0) return null;

  const label = humanizeLabel(name);

  if (Array.isArray(value) && value.some(isCriterionLike)) {
    return (
      <div className="wiring-setting">
        <div className="wiring-setting-label">{label}</div>
        <CriterionRows rules={value.filter(isCriterionLike)} />
      </div>
    );
  }
  if (
    isRecord(value) &&
    /blend|weights/.test(name) &&
    Object.values(value).every((v) => typeof v === 'number')
  ) {
    return (
      <div className="wiring-setting">
        <div className="wiring-setting-label">{label}</div>
        <div className="wiring-blend-line">{blendLine(value)}</div>
      </div>
    );
  }
  if (isRecord(value) && name === 'universe') {
    return <ScalarRow label={label} value={universeLine(value)} />;
  }
  if (Array.isArray(value) && value.every((v) => typeof v === 'string')) {
    return (
      <div className="wiring-setting">
        <div className="wiring-setting-label">{label}</div>
        <ChipRow items={value as string[]} />
      </div>
    );
  }
  if (Array.isArray(value) && value.every(isRecord)) {
    const labels = (value as SettingsRecord[])
      .map((o) =>
        typeof o.label === 'string' ? o.label : typeof o.name === 'string' ? o.name : null,
      )
      .filter((s): s is string => !!s);
    if (labels.length === value.length) {
      return (
        <div className="wiring-setting">
          <div className="wiring-setting-label">{label}</div>
          <ChipRow items={labels} />
        </div>
      );
    }
  }
  if (typeof value !== 'object') {
    return <ScalarRow label={label} value={settingValueText(name, value)} />;
  }
  if (isRecord(value)) {
    return (
      <div className="wiring-setting">
        <div className="wiring-setting-label">{label}</div>
        <GenericRecordRows record={value} />
      </div>
    );
  }
  return null;
}

const PROSE_KEYS = new Set(['research_emphasis', 'strategy_emphasis', 'north_star']);

function WiringSettingsList({ settings }: { settings: SettingsRecord }) {
  const entries = Object.entries(settings);
  const prose = entries.filter(([k, v]) => PROSE_KEYS.has(k) && typeof v === 'string');
  const rest = entries.filter(([k]) => !PROSE_KEYS.has(k));
  return (
    <div>
      {prose.map(([k, v]) => (
        <div className="wiring-setting" key={k}>
          <div className="wiring-setting-label">{humanizeLabel(k)}</div>
          <div className="wiring-prose">{String(v)}</div>
        </div>
      ))}
      {rest.map(([k, v]) => (
        <WiringSetting key={k} name={k} value={v} />
      ))}
    </div>
  );
}

export function WiringOverlay({ onClose }: { onClose: () => void }) {
  const [capability, setCapability] = useState('screener');
  const { data: strategy } = useQuery({ queryKey: ['strategy'], queryFn: getStrategy });
  const { data, isLoading, error } = useQuery({
    queryKey: ['wiring', capability],
    queryFn: () => getWiring(capability),
  });
  const v = strategy?.active_version;

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="panel-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="panel-sheet-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600 }}>
              Constitution {v ? `v${v.version_number}` : ''}
            </span>
            <span className="locked-tag">read-only · change it in conversation</span>
          </div>
          <button className="reader-popup-close" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="panel-sheet-body">
          {v?.north_star && (
            <p style={{ margin: '0 0 10px', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {v.north_star}
            </p>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
            {CAPABILITIES.map((c) => (
              <button
                key={c.key}
                className="cap-chip"
                style={capability === c.key
                  ? { background: 'var(--teal-bg)', color: 'var(--teal-ink)', borderColor: 'transparent' }
                  : undefined}
                onClick={() => setCapability(c.key)}
              >
                {c.label}
              </button>
            ))}
          </div>
          {isLoading && <div className="empty-note">Loading wiring…</div>}
          {error != null && (
            <div className="empty-note">
              No wiring yet — capabilities are configured once a Constitution is active.
            </div>
          )}
          {data && (
            <>
              {data.summary_text && (
                <p style={{ margin: '0 0 12px', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  {data.summary_text}
                </p>
              )}
              {Object.keys(data.settings ?? {}).length > 0 && (
                <div className="locked-panel" style={{ padding: '10px 12px', marginBottom: 12 }}>
                  <WiringSettingsList settings={data.settings} />
                </div>
              )}
              {(data.review_items?.length ?? 0) > 0 && (
                <>
                  <div className="draft-section-label">Needs review</div>
                  {data.review_items.map((item, i) => (
                    <div key={i} className="draft-tradeoff">
                      {item}
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>
        <div className="panel-sheet-foot">
          Derived from the approved rules — propose changes in conversation; nothing wires without your approval.
        </div>
      </div>
    </div>
  );
}
