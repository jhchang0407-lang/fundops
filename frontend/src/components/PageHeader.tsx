import type { ReactNode } from 'react';

interface PageHeaderProps {
  sectionLabel: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function PageHeader({ sectionLabel, title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div>
        <div className="section-label">{sectionLabel}</div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{actions}</div>}
    </div>
  );
}

export default PageHeader;
