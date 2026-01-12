/**
 * VerticalMenu Component
 * Nutzt zentrale MenuRenderer-Logik für identisches Verhalten
 */

import React, { useState } from 'react';
import type { MenuItem, MenuGroup } from '../../api/menu';
import { MenuRenderer } from './MenuRenderer';
import './VerticalMenu.css';

interface VerticalMenuProps {
  vertikalMenu: MenuGroup;
  onMenuClick: (item: MenuItem) => void;
}

export const VerticalMenu: React.FC<VerticalMenuProps> = ({
  vertikalMenu,
  onMenuClick
}) => {
  const [openSubmenus, setOpenSubmenus] = useState<Set<string>>(new Set());

  return (
    <aside className="vertical-menu">
      <div className="vertical-menu-container">
        <MenuRenderer
          menuData={vertikalMenu}
          orientation="vertical"
          openSubmenus={openSubmenus}
          setOpenSubmenus={setOpenSubmenus}
          onMenuClick={onMenuClick}
        />
      </div>
    </aside>
  );
};
