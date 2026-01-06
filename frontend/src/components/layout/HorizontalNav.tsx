/**
 * HorizontalNav Component
 * Horizontales Tab-Menü mit Zusatzmenü
 */
import React from 'react';

export const HorizontalNav: React.FC = () => {
  return (
    <nav className="horizontal-nav">
      <div style={{ padding: '0.75rem 1rem', color: 'var(--color-text-primary)' }}>
        <span>Grundmenü | Zusatzmenü</span>
      </div>
    </nav>
  );
};
