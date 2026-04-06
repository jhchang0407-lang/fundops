import type { ReactNode } from 'react';

interface KpiCardProps {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  valueColor?: string;
}

export function KpiCard({ label, value, detail, valueColor }: KpiCardProps) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={valueColor ? { color: valueColor } : undefined}>
        {value}
      </div>
      {detail && <div className="kpi-detail">{detail}</div>}
    </div>
  );
}

interface KpiRowProps {
  children: ReactNode;
  columns?: number;
}

export function KpiRow({ children, columns = 4 }: KpiRowProps) {
  return (
    <div
      className="kpi-grid"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}

export default KpiCard;
