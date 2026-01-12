/**
 * Menu API Service
 * Lädt Menüs über Backend API
 */

import axios from 'axios';

const API_URL = 'http://localhost:8000/api';

export interface MenuItem {
  guid?: string;
  type: 'BUTTON' | 'SUBMENU' | 'SEPARATOR' | 'SPACER';
  label: string;
  icon: string | null;
  tooltip: string | null;
  enabled: boolean;
  visible: boolean;
  sort_order: number;
  parent_guid: string | null;
  template_guid: string | null;
  command: {
    handler: string;
    params: Record<string, any>;
  } | null;
}

export interface MenuGroup {
  [itemGuid: string]: MenuItem;
}

export interface MenuData {
  ROOT?: {
    NAME?: string;
    GRUND?: string;
    VERTIKAL?: string;
    [key: string]: any;
  };
  GRUND?: MenuGroup;
  VERTIKAL?: MenuGroup;
  [key: string]: any;
}

export interface MenuResponse {
  uid: string;
  name: string;
  menu_data: MenuData;
  error?: string;
  message?: string;
}

/**
 * Lädt das Startmenü des Users
 */
export async function loadStartMenu(): Promise<MenuResponse> {
  const token = localStorage.getItem('token');
  
  if (!token) {
    throw new Error('Nicht angemeldet');
  }
  
  const response = await axios.get<MenuResponse>(
    `${API_URL}/menu/start`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  return response.data;
}

/**
 * Lädt ein App-Menü (z.B. PERSONALWESEN, ADMINISTRATION)
 */
export async function loadAppMenu(appName: string): Promise<MenuResponse> {
  const token = localStorage.getItem('token');
  
  if (!token) {
    throw new Error('Nicht angemeldet');
  }
  
  const response = await axios.get<MenuResponse>(
    `${API_URL}/menu/app/${appName}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  return response.data;
}

/**
 * Logout - Beendet Session
 */
export async function logout(): Promise<void> {
  const token = localStorage.getItem('token');
  
  if (!token) {
    return;
  }
  
  try {
    await axios.post(
      `${API_URL}/auth/logout`,
      {},
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );
  } finally {
    // Token immer löschen, auch bei Fehler
    localStorage.removeItem('token');
    localStorage.removeItem('selectedMandant');
  }
}
