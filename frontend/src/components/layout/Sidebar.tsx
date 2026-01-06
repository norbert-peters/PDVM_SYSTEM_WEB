/**
 * Sidebar Component
 * Vertikales Navigationsmenü
 */
import React from 'react';

interface SidebarProps {
  collapsed: boolean;
  open: boolean;
  onToggle: () => void;
  onOpenChange: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ collapsed, open }) => {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${open ? 'open' : ''}`}>
      <nav className="sidebar-nav">
        <div style={{ padding: '1rem', color: 'var(--color-text-primary)' }}>
          <h3>Apps</h3>
          <p style={{ fontSize: '0.875rem', opacity: 0.7 }}>Menüs werden geladen...</p>
        </div>
      </nav>
    </aside>
  );
};
