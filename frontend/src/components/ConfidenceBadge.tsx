/**
 * ConfidenceBadge — inline grounding confidence indicator.
 * Shows a colored dot + percentage text.
 * ≥0.7 green (high), 0.4-0.7 amber (medium), <0.4 red (low)
 */
export default function ConfidenceBadge({ confidence, label }: { confidence: number; label?: string }) {
  const level = confidence >= 0.7 ? 'high' : confidence >= 0.4 ? 'medium' : 'low';
  const pct = Math.round(confidence * 100);

  return (
    <span className="confidence-badge" title={label || `Grounding confidence: ${pct}%`}>
      <span className={`dot ${level}`} />
      <span style={{ color: 'var(--text-muted)' }}>{pct}%</span>
    </span>
  );
}
