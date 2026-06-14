/**
 * Structured result blocks inside assistant replies: data tables and price
 * charts returned by the chat analyst's tools. Table cell values arrive
 * pre-formatted from the backend (unit-aware), so they render verbatim.
 */

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ChatBlock } from '../../api/client';

function downloadCsv(block: Extract<ChatBlock, { type: 'table' }>) {
  const esc = (v: unknown) => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [
    block.columns.map((c) => esc(c.label)).join(','),
    ...block.rows.map((r) => block.columns.map((c) => esc(r[c.key])).join(',')),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${block.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function DataTableBlock({
  block,
}: {
  block: Extract<ChatBlock, { type: 'table' }>;
}) {
  if (!block.rows?.length) return null;
  return (
    <div className="chat-block">
      <div className="chat-block-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span>{block.title}</span>
        <button
          onClick={() => downloadCsv(block)}
          title="Download this table as CSV"
          style={{
            marginLeft: 'auto',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-data)',
            fontSize: 9,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
          }}
        >
          CSV ↓
        </button>
      </div>
      <div className="table-shell" style={{ boxShadow: 'none', overflowX: 'auto' }}>
        <table className="chat-block-table">
          <thead>
            <tr>
              {block.columns.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, i) => (
              <tr key={i}>
                {block.columns.map((c) => (
                  <td key={c.key}>{row[c.key] ?? '—'}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value?: number }[];
  label?: string;
}) {
  if (!active || !payload?.length || payload[0].value == null) return null;
  return (
    <div className="chat-chart-tooltip">
      <div>{label}</div>
      <div style={{ fontWeight: 600 }}>${payload[0].value.toFixed(2)}</div>
    </div>
  );
}

export function PriceChartBlock({
  block,
}: {
  block: Extract<ChatBlock, { type: 'chart' }>;
}) {
  if (!block.points?.length) return null;
  return (
    <div className="chat-block">
      <div className="chat-block-title">{block.title}</div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={block.points} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="chatPriceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.25} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: 'var(--text-muted)' }}
            tickLine={false}
            axisLine={false}
            minTickGap={48}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fontSize: 9, fill: 'var(--text-muted)' }}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip content={<ChartTooltip />} />
          <Area
            type="monotone"
            dataKey="close"
            stroke="var(--accent)"
            strokeWidth={1.5}
            fill="url(#chatPriceFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ChatBlocks({ blocks }: { blocks?: ChatBlock[] }) {
  if (!blocks?.length) return null;
  return (
    <>
      {blocks.map((b, i) =>
        b.type === 'table' ? (
          <DataTableBlock key={i} block={b} />
        ) : (
          <PriceChartBlock key={i} block={b} />
        ),
      )}
    </>
  );
}
