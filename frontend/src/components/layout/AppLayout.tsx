/**
 * AppLayout Component
 * Haupt-Layout-Container mit Header, Sidebar und Content
 */
import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Header } from './Header';
import { StichtagsBar } from './StichtagsBar';
import { Sidebar } from './Sidebar';
import { HorizontalNav } from './HorizontalNav';
import { useTheme } from '../../hooks/useTheme';
import { useMenu } from '../../contexts/MenuContext';
import { HorizontalMenu } from '../menu/HorizontalMenu';
import { VerticalMenu } from '../menu/VerticalMenu';
import { executeMenuCommand } from '../../utils/menuHandlers';
import { restoreLastNavigation } from '../../utils/menuHandlers';
import type { MenuItem } from '../../api/menu';

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const isDialogRoute = location.pathname.startsWith('/dialog/');
  const isViewRoute = location.pathname.startsWith('/view/');
  const menu = useMenu();
  
  // Theme loading in background - don't block rendering
  try {
    useTheme();
  } catch (error) {
    console.error('Theme loading error:', error);
  }
  
  // Lade Startmenü nach Mount
  useEffect(() => {
    if (menu.currentMenu || menu.loading) return

    ;(async () => {
      const restored = await restoreLastNavigation({
        setCurrentMenu: menu.setCurrentMenu,
        setCurrentApp: menu.setCurrentApp,
        navigate,
        showError: (msg) => menu.setError(msg),
      })

      if (!restored) {
        await menu.loadStart()
      } else {
        setInfoMessage('Letzte Sitzung wiederhergestellt.')
      }
    })()
  }, []);

  // Info-Toast automatisch ausblenden
  useEffect(() => {
    if (!infoMessage) return
    const t = window.setTimeout(() => setInfoMessage(null), 6000)
    return () => window.clearTimeout(t)
  }, [infoMessage])

  // Wenn sich die Route ändert, alten Fehler-Toast zurücksetzen
  useEffect(() => {
    if (menu.error) {
      menu.setError(null);
    }
  }, [location.pathname]);
  
  // Menu Handler Context
  const handleMenuClick = async (item: MenuItem) => {
    // Nächste Aktion -> Fehlermeldung ausblenden
    if (menu.error) {
      menu.setError(null);
    }

    await executeMenuCommand(item, {
      setCurrentMenu: menu.setCurrentMenu,
      setCurrentApp: menu.setCurrentApp,
      navigate,
      showError: (msg) => menu.setError(msg),
    });
  };
  
  // DEBUG: Log menu state
  console.log('🔍 AppLayout - Menu State:', {
    hasMenu: !!menu.currentMenu,
    hasVERTIKAL: !!menu.currentMenu?.VERTIKAL,
    vertikalKeys: menu.currentMenu?.VERTIKAL ? Object.keys(menu.currentMenu.VERTIKAL).length : 0,
    currentApp: menu.currentApp
  });

  return (
    <div className="app-layout">
      <Header />

      {/* Stichtagsbar als eigene Layout-Zeile unter dem Header */}
      <div className="stichtags-row">
        <StichtagsBar />
      </div>
      
      {/* Horizontales Menü (GRUND) */}
      {menu.currentMenu && (
        <HorizontalMenu
          grundMenu={menu.currentMenu.GRUND || {}}
          onMenuClick={handleMenuClick}
        />
      )}
      
      <div className="main-container">
        {/* Vertikales Menü (Sidebar) */}
        {menu.currentMenu && menu.currentMenu.VERTIKAL && Object.keys(menu.currentMenu.VERTIKAL).length > 0 && (
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
          
          <div
            className={`content-wrapper ${isDialogRoute ? 'content-wrapper--no-scroll' : isViewRoute ? 'content-wrapper--no-scroll-view' : ''}`}
          >
            {/* Info-Anzeige */}
            {infoMessage ? (
              <div className="menu-info">
                <button
                  type="button"
                  className="menu-info-close"
                  aria-label="Info schließen"
                  onClick={() => setInfoMessage(null)}
                >
                  ×
                </button>
                {infoMessage}
              </div>
            ) : null}

            {/* Fehler-Anzeige */}
            {menu.error && (
              <div className="menu-error">
                <button
                  type="button"
                  className="menu-error-close"
                  aria-label="Fehlermeldung schließen"
                  onClick={() => menu.setError(null)}
                >
                  ×
                </button>
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
