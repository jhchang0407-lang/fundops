interface HealthDotProps {
  score: number;
  showScore?: boolean;
}

export function HealthDot({ score, showScore = false }: HealthDotProps) {
  const level = score >= 70 ? 'positive' : score >= 40 ? 'warning' : 'negative';

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span className={`health-dot health-dot-${level}`} />
      {showScore && (
        <span style={{
          fontFamily: 'var(--font-data)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-secondary)',
        }}>
          {score}
        </span>
      )}
    </span>
  );
}

export default HealthDot;
