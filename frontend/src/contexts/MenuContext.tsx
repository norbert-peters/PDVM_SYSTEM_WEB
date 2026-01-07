/**
 * MenuContext - Global Menu State Management
 */

import { createContext, useContext, useState, ReactNode } from 'react';
import type { MenuData } from '../api/menu';
import { loadStartMenu, loadAppMenu } from '../api/menu';

interface MenuContextType {
  currentMenu: MenuData | null;
  currentApp: string | null;
  loading: boolean;
  error: string | null;
  
  setCurrentMenu: (menu: MenuData | null) => void;
  setCurrentApp: (appName: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  
  loadStart: () => Promise<void>;
  loadApp: (appName: string) => Promise<void>;
  clearMenu: () => void;
}

const MenuContext = createContext<MenuContextType | null>(null);

export function useMenu(): MenuContextType {
  const context = useContext(MenuContext);
  if (!context) {
    throw new Error('useMenu must be used within MenuProvider');
  }
  return context;
}

interface MenuProviderProps {
  children: ReactNode;
}

export function MenuProvider({ children }: MenuProviderProps) {
  const [currentMenu, setCurrentMenu] = useState<MenuData | null>(null);
  const [currentApp, setCurrentApp] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  
  /**
   * Lädt Startmenü
   */
  const loadStart = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await loadStartMenu();
      setCurrentMenu(response.menu_data);
      setCurrentApp(null);
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Fehler beim Laden des Startmenüs';
      setError(errorMsg);
      console.error('loadStart error:', err);
    } finally {
      setLoading(false);
    }
  };
  
  /**
   * Lädt App-Menü
   */
  const loadApp = async (appName: string): Promise<void> => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await loadAppMenu(appName);
      
      // Prüfe auf Berechtigungsfehler
      if (response.error === 'NO_PERMISSION') {
        setCurrentMenu(null);
        setCurrentApp(appName);
        setError(`Keine Berechtigung für ${appName}`);
        return;
      }
      
      if (response.error === 'NO_MENU') {
        setError(response.message || `Kein Menü für ${appName}`);
        return;
      }
      
      setCurrentMenu(response.menu_data);
      setCurrentApp(appName);
      
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || 'Fehler beim Laden des Menüs';
      setError(errorMsg);
      console.error('loadApp error:', err);
    } finally {
      setLoading(false);
    }
  };
  
  /**
   * Löscht aktuelles Menü
   */
  const clearMenu = (): void => {
    setCurrentMenu(null);
    setCurrentApp(null);
    setError(null);
  };
  
  const value: MenuContextType = {
    currentMenu,
    currentApp,
    loading,
    error,
    
    setCurrentMenu,
    setCurrentApp,
    setLoading,
    setError,
    
    loadStart,
    loadApp,
    clearMenu,
  };
  
  return (
    <MenuContext.Provider value={value}>
      {children}
    </MenuContext.Provider>
  );
}
