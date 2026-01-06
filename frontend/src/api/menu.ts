/**
 * Menu API Client
 * API-Aufrufe für Menü-Verwaltung
 */
import { apiClient } from './client';

export interface MenuItem {
  menu_item_guid: string;
  bezeichnung: string;
  ebene: number;
  prozess_guid?: string;
  button_guid?: string;
  menu_guid?: string;
  app_guid?: string;
  icon?: string;
  sort_order?: number;
  children?: MenuItem[];
}

export interface Menu {
  menu_guid: string;
  bezeichnung: string;
  menu_typ?: string;
  items?: MenuItem[];
}

export const menuApi = {
  /**
   * Lädt das Startmenü des aktuellen Benutzers
   */
  getUserStartMenu: async (): Promise<Menu> => {
    const response = await apiClient.get('/menu/user/start');
    return response.data;
  },

  /**
   * Lädt ein spezifisches Menü
   */
  getMenu: async (menuGuid: string): Promise<Menu> => {
    const response = await apiClient.get(`/menu/${menuGuid}`);
    return response.data;
  },

  /**
   * Lädt flache Menü-Items für ein Menü
   */
  getMenuItemsFlat: async (menuGuid: string): Promise<MenuItem[]> => {
    const response = await apiClient.get(`/menu/items/${menuGuid}/flat`);
    return response.data;
  },
};
