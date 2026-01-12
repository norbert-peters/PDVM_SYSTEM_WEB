/**
 * HorizontalMenu Component
 * Nutzt zentrale MenuRenderer-Logik für identisches Verhalten
 */

import React, { useState } from 'react';
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

  return (
    <nav className="horizontal-menu">
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
