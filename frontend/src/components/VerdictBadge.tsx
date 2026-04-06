type Verdict = 'pass' | 'no_pass' | 'pending';

interface VerdictBadgeProps {
  verdict: Verdict;
}

const classMap: Record<Verdict, string> = {
  pass: 'verdict-pass',
  no_pass: 'verdict-fail',
  pending: 'verdict-pending',
};

const labelMap: Record<Verdict, string> = {
  pass: 'PASS',
  no_pass: 'NO PASS',
  pending: 'PENDING',
};

export function VerdictBadge({ verdict }: VerdictBadgeProps) {
  return <span className={classMap[verdict]}>{labelMap[verdict]}</span>;
}

export default VerdictBadge;
