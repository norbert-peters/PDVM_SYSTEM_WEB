/**
 * AppLayout Component
 * Haupt-Layout-Container mit Header, Sidebar und Content
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { HorizontalNav } from './HorizontalNav';
import { useTheme } from '../../hooks/useTheme';
import { useMenu } from '../../contexts/MenuContext';
import { HorizontalMenu } from '../menu/HorizontalMenu';
import { VerticalMenu } from '../menu/VerticalMenu';
import { executeMenuCommand } from '../../utils/menuHandlers';
import { loadThemeColors, applyCSSVariables } from '../../api/theme';
import type { MenuItem } from '../../api/menu';

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const menu = useMenu();
  
  // Theme loading in background - don't block rendering
  try {
    useTheme();
  } catch (error) {
    console.error('Theme loading error:', error);
  }
  
  // Lade Startmenü nach Mount
  useEffect(() => {
    if (!menu.currentMenu && !menu.loading) {
      menu.loadStart();
    }
  }, []);
  
  // Lade Theme-Farben nach Mount
  useEffect(() => {
    const loadTheme = async () => {
      try {
        const themeData = await loadThemeColors();
        applyCSSVariables(themeData.colors);
        console.log('✅ Theme-Farben geladen:', themeData.theme_guid);
      } catch (error) {
        console.error('❌ Fehler beim Laden der Theme-Farben:', error);
      }
    };
    
    loadTheme();
  }, []);
  
  // Menu Handler Context
  const handleMenuClick = async (item: MenuItem) => {
    await executeMenuCommand(item, {
      setCurrentMenu: menu.setCurrentMenu,
      setCurrentApp: menu.setCurrentApp,
      navigate,
      showError: (msg) => menu.setError(msg),
    });
  };

  return (
    <div className="app-layout">
      <Header />
      
      {/* Horizontales Menü (GRUND + ZUSATZ) */}
      {menu.currentMenu && (
        <HorizontalMenu
          grundMenu={menu.currentMenu.GRUND || {}}
          zusatzMenu={menu.currentMenu.ZUSATZ || {}}
          onMenuClick={handleMenuClick}
        />
      )}
      
      <div className="main-container">
        {/* Vertikales Menü (Sidebar) */}
        {menu.currentMenu && menu.currentMenu.VERTIKAL && (
          <VerticalMenu
            vertikalMenu={menu.currentMenu.VERTIKAL}
            onMenuClick={handleMenuClick}
          />
        )}
        
        {/* Fallback: Standard-Sidebar wenn kein Menü geladen */}
        {!menu.currentMenu && (
          <Sidebar
            collapsed={sidebarCollapsed}
            open={sidebarOpen}
            onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
            onOpenChange={setSidebarOpen}
          />
        )}
        
        <div className="main-content">
          {/* Alte HorizontalNav nur wenn kein Menü */}
          {!menu.currentMenu && <HorizontalNav />}
          
          <div className="content-wrapper">
            {/* Fehler-Anzeige */}
            {menu.error && (
              <div className="menu-error">
                <strong>Fehler:</strong> {menu.error}
              </div>
            )}
            
            {/* Content */}
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};
