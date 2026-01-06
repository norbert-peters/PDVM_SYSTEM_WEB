/**
 * VerticalMenu Component
 * Vertikale Sidebar (VERTIKAL) mit App-Buttons
 */

import React from 'react';
import type { MenuItem, MenuGroup } from '../../api/menu';
import './VerticalMenu.css';

interface VerticalMenuProps {
  vertikalMenu: MenuGroup;
  onMenuClick: (item: MenuItem) => void;
}

export const VerticalMenu: React.FC<VerticalMenuProps> = ({
  vertikalMenu,
  onMenuClick
}) => {
  // Sortiere Items nach sort_order
  const sortedItems = Object.entries(vertikalMenu)
    .filter(([_, item]) => item.visible)
    .sort(([_, a], [__, b]) => a.sort_order - b.sort_order);

  const handleItemClick = (item: MenuItem) => {
    if (item.type === 'BUTTON' && item.enabled) {
      onMenuClick(item);
    }
  };

  const renderMenuItem = (guid: string, item: MenuItem) => {
    if (item.type === 'SEPARATOR') {
      return (
        <div key={guid} className="vertical-menu-separator">
          <hr />
        </div>
      );
    }

    if (item.type === 'BUTTON') {
      return (
        <button
          key={guid}
          className="vertical-menu-button"
          onClick={() => handleItemClick(item)}
          disabled={!item.enabled}
          title={item.tooltip || undefined}
        >
          {item.icon && <span className="menu-icon">{item.icon}</span>}
          <span className="menu-label">{item.label}</span>
        </button>
      );
    }

    return null;
  };

  return (
    <aside className="vertical-menu">
      <div className="vertical-menu-container">
        {sortedItems.map(([guid, item]) => renderMenuItem(guid, item))}
      </div>
    </aside>
  );
};
