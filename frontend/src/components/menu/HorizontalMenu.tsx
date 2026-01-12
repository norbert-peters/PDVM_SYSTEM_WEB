/**
 * HorizontalMenu Component
 * Nutzt zentrale MenuRenderer-Logik für identisches Verhalten
 */

import React, { useState, useEffect, useRef } from 'react';
import type { MenuItem, MenuGroup } from '../../api/menu';
import { MenuRenderer } from './MenuRenderer';
import './HorizontalMenu.css';

interface HorizontalMenuProps {
  grundMenu: MenuGroup;
  onMenuClick: (item: MenuItem) => void;
}

export const HorizontalMenu: React.FC<HorizontalMenuProps> = ({
  grundMenu,
  onMenuClick
}) => {
  const [openSubmenus, setOpenSubmenus] = useState<Set<string>>(new Set());
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpenSubmenus(new Set());
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <nav className="horizontal-menu" ref={menuRef}>
      <div className="horizontal-menu-container">
        <MenuRenderer
          menuData={grundMenu}
          orientation="horizontal"
          openSubmenus={openSubmenus}
          setOpenSubmenus={setOpenSubmenus}
          onMenuClick={onMenuClick}
        />
      </div>
    </nav>
  );
};
