type Status = 'held' | 'exited' | 'watchlist' | 'researched';

interface StatusBadgeProps {
  status: Status;
}

const classMap: Record<Status, string> = {
  held: 'status-badge status-held',
  exited: 'status-badge status-exited',
  watchlist: 'status-badge status-watchlist',
  researched: 'status-badge status-researched',
};

const labelMap: Record<Status, string> = {
  held: 'HELD',
  exited: 'EXITED',
  watchlist: 'WATCHLIST',
  researched: 'RESEARCHED',
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={classMap[status]}>{labelMap[status]}</span>;
}

export default StatusBadge;
