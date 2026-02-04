/**
 * Menu Handler System
 * Verarbeitet Menu-Commands (open_app_menu, logout, open_start_menu)
 */

import type { MenuItem } from '../api/menu';
import { loadAppMenu, loadStartMenu, logout as apiLogout, getLastNavigation, putLastNavigation } from '../api/menu';

type LastMenuContext = { menu_type: 'start' | 'app'; app_name?: string | null }

let lastMenuContext: LastMenuContext = { menu_type: 'start', app_name: null }

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
    console.log('🎯 App-Menü geladen für', appName, ':', menuResponse.menu_data);
    console.log('   GRUND:', Object.keys(menuResponse.menu_data?.GRUND || {}).length, 'Items');
    console.log('   VERTIKAL:', Object.keys(menuResponse.menu_data?.VERTIKAL || {}).length, 'Items');
    
    context.setCurrentMenu(menuResponse.menu_data);
    context.setCurrentApp(appName);

    lastMenuContext = { menu_type: 'app', app_name: appName };

    // UX: Beim Menüwechsel immer eine Startseite anzeigen
    context.navigate('/menu-home');
    
  } catch (error: any) {
    context.showError(error.response?.data?.detail || error.message || 'Fehler beim Laden des Menüs');
  }
}

/**
 * Handler: logout
 * Beendet Session und geht zurück zum Login
 */
async function handleLogout(_item: MenuItem, _context: MenuHandlerContext): Promise<void> {
  try {
    await apiLogout();
    
    // Hard Reload zum Login (löscht kompletten React-State)
    window.location.href = '/login';
    
  } catch (error: any) {
    console.error('Logout-Fehler:', error);
    // Auch bei Fehler zum Login (Token ist gelöscht)
    window.location.href = '/login';
  }
}

/**
 * Handler: open_start_menu
 * Lädt Startmenü neu
 */
async function handleOpenStartMenu(_item: MenuItem, context: MenuHandlerContext): Promise<void> {
  try {
    const menuResponse = await loadStartMenu();
    
    context.setCurrentMenu(menuResponse.menu_data);
    context.setCurrentApp(null);

    lastMenuContext = { menu_type: 'start', app_name: null };

    // UX: Beim Menüwechsel immer eine Startseite anzeigen
    context.navigate('/menu-home');
    
  } catch (error: any) {
    context.showError(error.response?.data?.detail || error.message || 'Fehler beim Laden des Startmenüs');
  }
}

/**
 * Handler: show_help
 * Zeigt Hilfe-Dialog (TODO: Implementierung)
 */
async function handleShowHelp(item: MenuItem, _context: MenuHandlerContext): Promise<void> {
  const helpText = item.command?.params?.help_text || 'Hilfe';
  const helpType = item.command?.params?.help_type || 'dialog';
  
  // TODO: Hilfe-Dialog implementieren
  _context.showError(`Hilfe (${helpType}): ${helpText}`);
}

/**
 * Handler: go_view
 * Öffnet eine View per GUID (Route /view/:viewGuid)
 */
async function handleGoView(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  const viewGuid = item.command?.params?.view_guid || item.command?.params?.guid;

  if (!viewGuid) {
    context.showError('Kein view_guid im Command gefunden');
    return;
  }

  context.navigate(`/view/${viewGuid}`);
}

/**
 * Handler: go_dialog
 * Öffnet einen Dialog per GUID (Route /dialog/:dialogGuid)
 */
async function handleGoDialog(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  const dialogGuid = item.command?.params?.dialog_guid || item.command?.params?.guid;
  const dialogTable = item.command?.params?.dialog_table || item.command?.params?.table || item.command?.params?.root_table;

  if (!dialogGuid) {
    context.showError('Kein dialog_guid im Command gefunden');
    return;
  }

  const qs = dialogTable ? `?dialog_table=${encodeURIComponent(String(dialogTable))}` : '';
  context.navigate(`/dialog/${dialogGuid}${qs}`);
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
  'go_view': handleGoView,
  'go_dialog': handleGoDialog,
};

/**
 * Führt Menu-Command aus
 */
export async function executeMenuCommand(item: MenuItem, context: MenuHandlerContext): Promise<void> {
  if (!item.command || !item.command.handler) {
    context.showError('Kein Kommando vorhanden');
    return;
  }
  
  const handler = HANDLERS[item.command.handler];
  
  if (!handler) {
    context.showError(`Unbekannter Handler: ${item.command.handler}`);
    return;
  }
  
  await handler(item, context);

  // Persistenz: letzte Menü-Navigation + letztes Command (außer logout)
  try {
    const cmd = item.command
    if (!cmd || !cmd.handler) return
    if (cmd.handler === 'logout') return

    // Für Menü-Wechsel den Context hart setzen
    if (cmd.handler === 'open_app_menu') {
      const appName = cmd.params?.app_name ? String(cmd.params.app_name) : null
      lastMenuContext = { menu_type: 'app', app_name: appName }
    } else if (cmd.handler === 'open_start_menu') {
      lastMenuContext = { menu_type: 'start', app_name: null }
    }

    await putLastNavigation({
      menu_type: lastMenuContext.menu_type,
      app_name: lastMenuContext.app_name ?? null,
      command: { handler: String(cmd.handler), params: (cmd.params || {}) as any },
    })
  } catch {
    // Best effort
  }
}

export async function restoreLastNavigation(context: MenuHandlerContext): Promise<boolean> {
  try {
    const state = await getLastNavigation()
    const menuType = (state?.menu_type || 'start') as 'start' | 'app'
    const appName = state?.app_name ? String(state.app_name) : null
    const cmd = state?.command || null

    // 1) Menü wiederherstellen
    if (menuType === 'app' && appName) {
      const menuResponse = await loadAppMenu(appName)
      if (menuResponse.error) throw new Error(menuResponse.message || menuResponse.error)
      context.setCurrentMenu(menuResponse.menu_data)
      context.setCurrentApp(appName)
      lastMenuContext = { menu_type: 'app', app_name: appName }
    } else {
      const menuResponse = await loadStartMenu()
      context.setCurrentMenu(menuResponse.menu_data)
      context.setCurrentApp(null)
      lastMenuContext = { menu_type: 'start', app_name: null }
    }

    // 2) letztes Command wieder ausführen (nur sichere Navigation)
    //    -> verhindert, dass wir ungewollt "Aktionen" erneut triggern.
    if (cmd && cmd.handler && cmd.handler !== 'logout') {
      const handler = String(cmd.handler)
      const params = (cmd.params || {}) as any

      if (handler === 'go_view') {
        const viewGuid = params?.view_guid || params?.guid
        if (viewGuid) {
          context.navigate(`/view/${String(viewGuid)}`)
          return true
        }
      }

      if (handler === 'go_dialog') {
        const dialogGuid = params?.dialog_guid || params?.guid
        const dialogTable = params?.dialog_table || params?.table || params?.root_table
        if (dialogGuid) {
          const qs = dialogTable ? `?dialog_table=${encodeURIComponent(String(dialogTable))}` : ''
          context.navigate(`/dialog/${String(dialogGuid)}${qs}`)
          return true
        }
      }
    }

    // Wenn kein (sicheres) Command vorhanden ist, wenigstens Startseite zeigen
    context.navigate('/menu-home')
    return true
  } catch {
    return false
  }
}
