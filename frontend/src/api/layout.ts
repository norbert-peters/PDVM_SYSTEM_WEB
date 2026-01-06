/**
 * Layout API Client
 * Kommunikation mit Backend Layout-Endpoints
 */
import { apiClient } from './client';

export interface LayoutResponse {
  // Direkte Theme-Daten (Backend gibt ohne daten-Wrapper zurück)
  mandant_uid: string;
  mandant_name: string;
  theme: 'light' | 'dark';
  colors: Record<string, any>;
  typography: Record<string, any>;
  customizations: Record<string, any>;
  assets: Record<string, any>;
}

export const layoutApi = {
  /**
   * Lädt alle Layouts für einen Mandanten
   */
  getMandantLayouts: async (mandantUid: string): Promise<LayoutResponse[]> => {
    const response = await apiClient.get(`/layout/${mandantUid}`);
    return response.data.layouts || [];
  },

  /**
   * Lädt spezifisches Theme für einen Mandanten
   */
  getMandantTheme: async (
    mandantUid: string,
    theme: 'light' | 'dark'
  ): Promise<LayoutResponse> => {
    const response = await apiClient.get(`/layout/${mandantUid}/${theme}`);
    return response.data;
  },

  /**
   * Aktualisiert Theme-Konfiguration
   */
  updateMandantTheme: async (
    mandantUid: string,
    theme: 'light' | 'dark',
    layoutData: Record<string, any>
  ): Promise<LayoutResponse> => {
    const response = await apiClient.put(`/layout/${mandantUid}/${theme}`, layoutData);
    return response.data;
  },

  /**
   * Lädt Theme für den aktuell angemeldeten Mandanten
   */
  getCurrentTheme: async (theme: 'light' | 'dark' = 'light'): Promise<LayoutResponse> => {
    const response = await apiClient.get(`/layout/current/theme?theme=${theme}`);
    return response.data;
  },

  /**
   * Speichert Theme-Präferenz (light/dark) in Systemsteuerung
   */
  saveThemePreference: async (themeMode: 'light' | 'dark'): Promise<void> => {
    await apiClient.post('/layout/preferences/theme', null, {
      params: { theme_mode: themeMode }
    });
  },

  /**
   * Lädt gespeicherte Theme-Präferenz aus Systemsteuerung
   */
  getThemePreference: async (): Promise<'light' | 'dark'> => {
    const response = await apiClient.get('/layout/preferences/theme');
    return response.data.theme_mode || 'light';
  },
};
