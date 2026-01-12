/**
 * MenuRenderer - Zentrale generische Menü-Rendering-Logik
 * Wird von BEIDEN Menüs (horizontal + vertikal) verwendet
 * Identisches Verhalten: Dropdown bis max. 5 Ebenen, schließt bei BUTTON-Klick
 */

import React from 'react';
import type { MenuItem, MenuGroup } from '../../api/menu';

export const MAX_DEPTH = 5;

interface MenuRendererProps {
  menuData: MenuGroup;
  orientation: 'horizontal' | 'vertical';
  openSubmenus: Set<string>;
  setOpenSubmenus: (submenus: Set<string>) => void;
  onMenuClick: (item: MenuItem) => void;
}

export const MenuRenderer: React.FC<MenuRendererProps> = ({
  menuData,
  orientation,
  openSubmenus,
  setOpenSubmenus,
  onMenuClick
}) => {
  
  // Hole Children für ein Parent
  const getChildren = (parentGuid: string | null): [string, MenuItem][] => {
    return Object.entries(menuData)
      .filter(([_, item]) => {
        if (parentGuid === null) {
          return !item.parent_guid && item.visible;
        }
        return item.parent_guid === parentGuid && item.visible;
      })
      .sort(([_, a], [__, b]) => (a.sort_order || 0) - (b.sort_order || 0));
  };

  // Handler für Menü-Klick
  const handleItemClick = (guid: string, item: MenuItem) => {
    if (item.type === 'SUBMENU') {
      const wasOpen = openSubmenus.has(guid);
      const newSubmenus = new Set(openSubmenus);
      
      if (!wasOpen) {
        // Öffne dieses Submenu (Parent bleibt offen)
        newSubmenus.add(guid);
        console.log(`🔼 Öffne Submenu: ${item.label}`);
      } else {
        // Schließe dieses Submenu und alle seine Kinder
        const toClose = new Set([guid]);
        
        // Finde alle Kinder rekursiv
        const findChildren = (parentGuid: string) => {
          Object.entries(menuData).forEach(([childGuid, childItem]) => {
            if (childItem.parent_guid === parentGuid) {
              toClose.add(childGuid);
              findChildren(childGuid);
            }
          });
        };
        findChildren(guid);
        
        // Entferne alle gefundenen aus openSubmenus
        toClose.forEach(g => newSubmenus.delete(g));
        console.log(`🔽 Schließe Submenu: ${item.label} + ${toClose.size - 1} Kinder`);
      }
      
      setOpenSubmenus(newSubmenus);
    } else if (item.type === 'BUTTON') {
      // Execute Handler und schließe ALLE Submenüs
      console.log(`✅ Button: ${item.label}`);
      onMenuClick(item);
      setOpenSubmenus(new Set());
    }
  };

  // Rekursives Rendering eines Menü-Items
  const renderMenuItem = (guid: string, item: MenuItem, depth: number = 0): React.ReactNode => {
    if (depth >= MAX_DEPTH) return null;
    if (!item.visible) return null;

    const children = getChildren(guid);
    const isOpen = openSubmenus.has(guid);
    const hasChildren = children.length > 0;

    // DEBUG: Log bei Submenus
    if (item.type === 'SUBMENU' && depth === 0) {
      console.log(`📋 Submenu "${item.label}": ${children.length} Kinder, isOpen: ${isOpen}`);
    }

    // SEPARATOR
    if (item.type === 'SEPARATOR') {
      return (
        <div key={guid} className={`${orientation}-menu-separator`}>
          {orientation === 'horizontal' ? <div className="separator-line" /> : <hr />}
        </div>
      );
    }

    // SPACER - unsichtbar
    if (item.type === 'SPACER') {
      return null;
    }

    // SUBMENU
    if (item.type === 'SUBMENU') {
      return (
        <div key={guid} className={`${orientation}-menu-submenu ${depth > 0 ? 'nested' : ''}`}>
          <button
            className={`${orientation}-menu-button ${isOpen ? 'open' : ''} ${hasChildren ? 'has-children' : ''}`}
            onClick={() => handleItemClick(guid, item)}
            disabled={!item.enabled}
            title={item.tooltip || undefined}
          >
            {item.icon && <span className="menu-icon">{item.icon}</span>}
            <span className="menu-label">{item.label}</span>
            {hasChildren && <span className="submenu-arrow">{orientation === 'horizontal' ? '▼' : '▶'}</span>}
          </button>
          
          {isOpen && hasChildren && (
            <div className={`${orientation}-menu-dropdown ${depth > 0 ? 'nested-dropdown' : ''}`}>
              {(() => {
                console.log(`🎨 Rendere Dropdown für "${item.label}" mit ${children.length} Kindern`);
                return children.map(([childGuid, childItem]) =>
                  renderMenuItem(childGuid, childItem, depth + 1)
                );
              })()}
            </div>
          )}
        </div>
      );
    }

    // BUTTON
    if (item.type === 'BUTTON') {
      return (
        <button
          key={guid}
          className={`${orientation}-menu-button`}
          onClick={() => handleItemClick(guid, item)}
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

  // Top-Level Items rendern
  const topLevelItems = getChildren(null);

  if (topLevelItems.length === 0) {
    return (
      <div style={{ padding: orientation === 'horizontal' ? '0.75rem 1rem' : '1rem', color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
        Kein Menü
      </div>
    );
  }

  return (
    <>
      {topLevelItems.map(([guid, item]) => renderMenuItem(guid, item, 0))}
    </>
  );
};
