import type { ReactNode } from 'react';

interface ExpandableRowProps {
  isExpanded: boolean;
  onToggle: () => void;
  summaryColumns: ReactNode[];
  columnClasses?: (string | undefined)[];
  expandedContent: ReactNode;
  colSpan: number;
}

export function ExpandableRow({
  isExpanded,
  onToggle,
  summaryColumns,
  columnClasses,
  expandedContent,
  colSpan,
}: ExpandableRowProps) {
  return (
    <>
      <tr
        onClick={onToggle}
        style={{ cursor: 'pointer' }}
      >
        {summaryColumns.map((col, i) => (
          <td key={i} className={columnClasses?.[i]}>{col}</td>
        ))}
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={colSpan} style={{ padding: 0, borderBottom: '1px solid var(--border)' }}>
            <div className="expanded-area">
              <div className="expanded-cards">
                {expandedContent}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default ExpandableRow;
