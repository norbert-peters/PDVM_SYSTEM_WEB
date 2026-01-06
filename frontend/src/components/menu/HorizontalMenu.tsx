/**
 * HorizontalMenu Component
 * Horizontales Menü (GRUND + ZUSATZ) unterhalb Header
 * Rendert SUBMENU → BUTTON Hierarchie
 */

import React, { useState } from 'react';
import type { MenuItem, MenuGroup } from '../../api/menu';
import './HorizontalMenu.css';

interface HorizontalMenuProps {
  grundMenu: MenuGroup;
  zusatzMenu: MenuGroup;
  onMenuClick: (item: MenuItem) => void;
}

export const HorizontalMenu: React.FC<HorizontalMenuProps> = ({
  grundMenu,
  zusatzMenu,
  onMenuClick
}) => {
  const [openSubmenu, setOpenSubmenu] = useState<string | null>(null);

  // Kombiniere GRUND + ZUSATZ
  const combinedMenu = { ...grundMenu, ...zusatzMenu };

  // Filtere Top-Level Items (parent_guid = null)
  const topLevelItems = Object.entries(combinedMenu)
    .filter(([_, item]) => item.parent_guid === null && item.visible)
    .sort(([_, a], [__, b]) => a.sort_order - b.sort_order);

  // Hole Children für ein Parent
  const getChildren = (parentGuid: string): [string, MenuItem][] => {
    return Object.entries(combinedMenu)
      .filter(([_, item]) => item.parent_guid === parentGuid && item.visible)
      .sort(([_, a], [__, b]) => a.sort_order - b.sort_order);
  };

  const handleItemClick = (guid: string, item: MenuItem) => {
    if (item.type === 'SUBMENU') {
      // Toggle Submenu
      setOpenSubmenu(openSubmenu === guid ? null : guid);
    } else if (item.type === 'BUTTON') {
      // Execute Handler
      onMenuClick(item);
      setOpenSubmenu(null);
    }
  };

  const renderMenuItem = (guid: string, item: MenuItem, level: number = 0) => {
    const children = getChildren(guid);
    const isOpen = openSubmenu === guid;

    if (item.type === 'SEPARATOR') {
      return (
        <div key={guid} className="horizontal-menu-separator" />
      );
    }

    if (item.type === 'SUBMENU') {
      return (
        <div key={guid} className="horizontal-menu-submenu">
          <button
            className={`horizontal-menu-button ${isOpen ? 'open' : ''}`}
            onClick={() => handleItemClick(guid, item)}
            disabled={!item.enabled}
            title={item.tooltip || undefined}
          >
            {item.icon && <span className="menu-icon">{item.icon}</span>}
            <span>{item.label}</span>
            <span className="submenu-arrow">▼</span>
          </button>
          
          {isOpen && children.length > 0 && (
            <div className="horizontal-menu-dropdown">
              {children.map(([childGuid, childItem]) =>
                renderMenuItem(childGuid, childItem, level + 1)
              )}
            </div>
          )}
        </div>
      );
    }

    // BUTTON
    return (
      <button
        key={guid}
        className="horizontal-menu-button"
        onClick={() => handleItemClick(guid, item)}
        disabled={!item.enabled}
        title={item.tooltip || undefined}
      >
        {item.icon && <span className="menu-icon">{item.icon}</span>}
        <span>{item.label}</span>
      </button>
    );
  };

  return (
    <nav className="horizontal-menu">
      <div className="horizontal-menu-container">
        {topLevelItems.map(([guid, item]) => renderMenuItem(guid, item))}
      </div>
    </nav>
  );
};
