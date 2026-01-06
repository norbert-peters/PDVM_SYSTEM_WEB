/**
 * Menu Handler System
 * Verarbeitet Menu-Commands (open_app_menu, logout, open_start_menu)
 */

import type { MenuItem } from '../api/menu';
import { loadAppMenu, loadStartMenu, logout as apiLogout } from '../api/menu';

export type MenuHandler = (item: MenuItem, context: MenuHandlerContext) => Promise<void>;

export interface MenuHandlerContext {
  setCurrentMenu: (menu: any) => void;
  setCurrentApp: (appName: string | null) => void;
  navigate: (path: string) => void;
  showError: (message: string) => void;
}

/**
 * Handler: open_app_menu
 * Lädt ein App-Menü (z.B. PERSONALWESEN, ADMINISTRATION)
 */
async function handleOpenAppMenu(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  const appName = item.command?.params?.app_name;
  
  if (!appName) {
    context.showError('Kein App-Name im Command gefunden');
    return;
  }
  
  try {
    const menuResponse = await loadAppMenu(appName);
    
    // Prüfe auf Berechtigungsfehler
    if (menuResponse.error === 'NO_PERMISSION') {
      // Zeige "Keine Berechtigung" im Content-Bereich
      context.setCurrentApp(appName);
      context.setCurrentMenu(null);
      return;
    }
    
    if (menuResponse.error === 'NO_MENU') {
      context.showError(menuResponse.message || `Kein Menü für ${appName}`);
      return;
    }
    
    // Menü erfolgreich geladen
    context.setCurrentMenu(menuResponse.menu_data);
    context.setCurrentApp(appName);
    
  } catch (error: any) {
    context.showError(error.response?.data?.detail || error.message || 'Fehler beim Laden des Menüs');
  }
}

/**
 * Handler: logout
 * Beendet Session und geht zurück zum Login
 */
async function handleLogout(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  try {
    await apiLogout();
    
    // Zurück zum Login
    context.navigate('/login');
    
  } catch (error: any) {
    console.error('Logout-Fehler:', error);
    // Auch bei Fehler zum Login (Token ist gelöscht)
    context.navigate('/login');
  }
}

/**
 * Handler: open_start_menu
 * Lädt Startmenü neu
 */
async function handleOpenStartMenu(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  try {
    const menuResponse = await loadStartMenu();
    
    context.setCurrentMenu(menuResponse.menu_data);
    context.setCurrentApp(null);
    
  } catch (error: any) {
    context.showError(error.response?.data?.detail || error.message || 'Fehler beim Laden des Startmenüs');
  }
}

/**
 * Handler: show_help
 * Zeigt Hilfe-Dialog (TODO: Implementierung)
 */
async function handleShowHelp(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  const helpText = item.command?.params?.help_text || 'Hilfe';
  const helpType = item.command?.params?.help_type || 'dialog';
  
  // TODO: Hilfe-Dialog implementieren
  alert(`Hilfe: ${helpText}\nTyp: ${helpType}`);
}

/**
 * Handler Registry
 * Mappt handler-Namen zu Funktionen
 */
const HANDLERS: Record<string, MenuHandler> = {
  'open_app_menu': handleOpenAppMenu,
  'logout': handleLogout,
  'open_start_menu': handleOpenStartMenu,
  'show_help': handleShowHelp,
};

/**
 * Führt Menu-Command aus
 */
export async function executeMenuCommand(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  if (!item.command || !item.command.handler) {
    console.warn('Menu-Item hat kein Command:', item);
    return;
  }
  
  const handler = HANDLERS[item.command.handler];
  
  if (!handler) {
    context.showError(`Unbekannter Handler: ${item.command.handler}`);
    return;
  }
  
  await handler(item, context);
}
