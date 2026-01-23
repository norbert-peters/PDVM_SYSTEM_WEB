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
  activeItemGuid?: string | null;
  setActiveItemGuid?: (guid: string | null) => void;
}

export const MenuRenderer: React.FC<MenuRendererProps> = ({
  menuData,
  orientation,
  openSubmenus,
  setOpenSubmenus,
  onMenuClick,
  activeItemGuid,
  setActiveItemGuid
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
    try {
      setActiveItemGuid?.(guid)
    } catch {
      // ignore
    }

    if (item.type === 'SUBMENU') {
      const wasOpen = openSubmenus.has(guid);
      const newSubmenus = new Set(openSubmenus);
      
      if (!wasOpen) {
        // 1. Schließe alle Siblings (Items auf gleicher Ebene)
        const siblings = Object.entries(menuData).filter(([id, i]) => 
          i.parent_guid === item.parent_guid && id !== guid
        );
        
        // Rekursive Funktion zum Schließen eines Items und seiner Kinder
        const closeItemRecursively = (targetGuid: string) => {
          if (newSubmenus.has(targetGuid)) {
            newSubmenus.delete(targetGuid);
            // Suche Kinder
            Object.entries(menuData).forEach(([childGuid, childItem]) => {
              if (childItem.parent_guid === targetGuid) {
                closeItemRecursively(childGuid);
              }
            });
          }
        };

        siblings.forEach(([siblingGuid]) => closeItemRecursively(siblingGuid));

        // 2. Öffne dieses Submenu
        newSubmenus.add(guid);
        console.log(`🔼 Öffne Submenu: ${item.label}`);
      } else {
        // Schließe dieses Submenu und alle seine Kinder
        const closeItemRecursively = (targetGuid: string) => {
          newSubmenus.delete(targetGuid);
          Object.entries(menuData).forEach(([childGuid, childItem]) => {
            if (childItem.parent_guid === targetGuid) {
              closeItemRecursively(childGuid);
            }
          });
        };
        closeItemRecursively(guid);
        console.log(`🔽 Schließe Submenu: ${item.label}`);
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
            className={`${orientation}-menu-button ${isOpen ? 'open' : ''} ${hasChildren ? 'has-children' : ''} ${activeItemGuid === guid ? 'active' : ''}`}
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
          className={`${orientation}-menu-button ${activeItemGuid === guid ? 'active' : ''}`}
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
