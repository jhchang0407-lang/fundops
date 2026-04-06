/**
 * ThesisHealthBar — per-assumption thesis health display.
 * Shows horizontal pills colored by status (intact/at_risk/breach).
 */
type Assumption = {
  assumption: string;
  metric?: string | null;
  threshold?: number | null;
  current_value?: number | null;
  status: string; // "intact" | "at_risk" | "breach"
};

export default function ThesisHealthBar({
  assumptions,
  compact = false,
}: {
  assumptions: Assumption[];
  compact?: boolean;
}) {
  if (!assumptions || assumptions.length === 0) {
    return <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>No thesis assumptions tracked</span>;
  }

  return (
    <div className="thesis-health-bar">
      {assumptions.map((a, i) => {
        const statusClass = a.status === 'at_risk' ? 'at-risk' : a.status;
        const label = compact
          ? (a.metric || a.assumption.split(' ').slice(0, 2).join(' '))
          : a.assumption;

        return (
          <span
            key={i}
            className={`thesis-health-pill ${statusClass}`}
            title={`${a.assumption}${a.current_value != null ? ` (current: ${typeof a.current_value === 'number' ? (a.current_value * 100).toFixed(1) + '%' : a.current_value})` : ''}`}
          >
            {a.status === 'breach' ? '✗ ' : a.status === 'at_risk' ? '⚠ ' : '✓ '}
            {label}
          </span>
        );
      })}
    </div>
  );
}
