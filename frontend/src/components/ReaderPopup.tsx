import { type ReactNode, useEffect } from 'react';

interface ReaderPopupProps {
  title: ReactNode;
  children: ReactNode;
  onClose: () => void;
  headerActions?: ReactNode;
}

export function ReaderPopup({ title, children, onClose, headerActions }: ReaderPopupProps) {
  // Lock body scroll while open
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div className="reader-overlay" onClick={onClose}>
      <div className="reader-popup" onClick={e => e.stopPropagation()}>
        <div className="reader-popup-header">
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 'var(--text-base)' }}>
            {title}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {headerActions}
            <button className="reader-popup-close" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="reader-popup-body">
          {children}
        </div>
      </div>
    </div>
  );
}

export default ReaderPopup;
