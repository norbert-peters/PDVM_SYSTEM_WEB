/**
 * Layout API Client
 * Aufgeloestes Theme, Token-Katalog und Hell/Dunkel-Praeferenz
 */
import { apiClient } from './client';
import type { ThemeTokens } from '../utils/themeVars';

export type ThemeMode = 'light' | 'dark';

export interface ThemeBlock {
  [key: string]: string;
}

export interface ThemeContrastIssue {
  fg: string;
  bg: string;
  ratio: number;
  min: number;
  ok: boolean;
}

export interface ResolvedThemeResponse {
  theme_package_id: string | null;
  theme_variant: string;
  mode: ThemeMode;
  schema_version: number;
  blocks: Record<string, ThemeBlock>;
  layers: { mandant: boolean; user: boolean };
  contrast_issues: ThemeContrastIssue[];
  warnings: string[];
  /** Wirksame Layout-Varianten je Bereich (Strukturkatalog), z. B. { header: 'kompakt' } */
  layout?: Record<string, string>;
  layout_warnings?: string[];
}

export type ThemeControlType = 'color' | 'css_length' | 'css_border' | 'font_family' | 'string' | 'dropdown';

export interface ThemeTokenSpec {
  type: 'color' | 'length' | 'border' | 'shadow' | 'font' | 'number';
  user_editable: boolean;
  label: string;
  /** Typ des PdvmInputControl, aus dem Schema erzeugt */
  control_type: ThemeControlType;
  min?: number;
  max?: number;
  options?: string[];
  /** Gegenfarben mit Mindestkontrast (Ref = "<gruppe>.<token>") */
  contrast_against?: Array<{ ref: string; min: number }>;
}

export interface ThemeCatalogGroup {
  label: string;
  tokens: Record<string, ThemeTokenSpec>;
}

export interface ThemeCatalogResponse {
  schema_version: number;
  groups: Record<string, ThemeCatalogGroup>;
  /** Muster, die der Mandant für Benutzer freigeben kann (USER_THEME_EDIT) */
  user_edit_presets: Array<{ value: string; label: string }>;
  /** Pflicht-Kontrastpaare inkl. CSS-Fallback-Ketten */
  contrast_pairs: Array<{ fg: string; bg: string; min: number; fg_chain: string[]; bg_chain: string[] }>;
}

export type ThemeScope = 'mandant' | 'user';

export interface ThemeEditorModeState {
  variant: string | null;
  /** Basis der Ebene: Paket-Variante (Mandant) bzw. Paket + Mandanten-Overlay (Benutzer) */
  base: ThemeTokens;
  overlay: ThemeTokens;
  warnings: string[];
}

export interface ThemePackageInfo {
  guid: string;
  name: string;
  /** Standard-Paket des Mandanten (THEME_GUID) */
  is_default?: boolean;
}

export interface MandantThemeSettings {
  /** Standard-Paket (sys_layout-GUID) */
  theme_default: string;
  /** Zusätzlich für Benutzer wählbare Pakete (ohne das Standard-Paket) */
  theme_allowed: string[];
  theme_light: string;
  theme_dark: string;
  default_mode: '' | ThemeMode;
  user_theme_edit: string[];
  /** Mandanten-Vorgabe je Layout-Bereich ({bereich: variante}) */
  layout_default: Record<string, string>;
  /** Für Benutzer freigegebene Varianten ({bereich: [varianten]}) */
  layout_allowed: Record<string, string[]>;
}

export interface UserThemeSettings {
  /** Gewähltes Paket; leer = Standard-Paket des Mandanten */
  theme_choice: string;
  variant_light: string;
  variant_dark: string;
  mode: ThemeMode;
  layout_choice: Record<string, string>;
}

export interface LayoutAreaOption {
  value: string;
  label: string;
  description: string;
}

export interface LayoutArea {
  label: string;
  default: string;
  options: LayoutAreaOption[];
  /** Varianten, die auf dieser Ebene wählbar sind (Mandant: alle; Benutzer: Vorgabe + Freigaben) */
  available: string[];
  mandant_default: string;
}

export interface ThemeEditorState<S = MandantThemeSettings | UserThemeSettings> {
  scope: ThemeScope;
  theme_package_id: string | null;
  /** Für den Mandanten freigegebene Theme-Pakete (Standard zuerst) */
  packages: ThemePackageInfo[];
  variants: Record<ThemeMode, string[]>;
  modes: Record<ThemeMode, ThemeEditorModeState>;
  settings: S;
  layout: Record<string, LayoutArea>;
  /** Nur Benutzer-Ebene: vom Mandanten freigegebene Muster */
  allowed_patterns: string[] | null;
  can_edit_overlay: boolean;
}

export type ThemeOverlay = Partial<Record<ThemeMode, ThemeTokens>>;

export const layoutApi = {
  /**
   * Lädt das aktive Theme, serverseitig aus Paket, Mandanten- und Benutzer-Overlay aufgelöst.
   * Ohne Modus gilt die gespeicherte Benutzer-Präferenz.
   */
  getResolvedTheme: async (mode?: ThemeMode): Promise<ResolvedThemeResponse> => {
    const response = await apiClient.get('/layout/resolved', { params: mode ? { mode } : {} });
    return response.data;
  },

  /**
   * Lädt das vorgegebene Token-Schema (für Editoren)
   */
  getCatalog: async (): Promise<ThemeCatalogResponse> => {
    const response = await apiClient.get('/layout/catalog');
    return response.data;
  },

  /**
   * Speichert Theme-Präferenz (light/dark) in Systemsteuerung
   */
  saveThemePreference: async (themeMode: ThemeMode): Promise<void> => {
    await apiClient.post('/layout/preferences/theme', null, {
      params: { theme_mode: themeMode }
    });
  },

  /** Zustand des Theme-Editors; Ebene 'mandant' nur mit Rolle 'overlay'. ``packageGuid``: Vorschau eines anderen Pakets (Ebene 'user') */
  getEditorState: async (scope: ThemeScope, packageGuid?: string): Promise<ThemeEditorState> => {
    const response = await apiClient.get(`/layout/editor/${scope}`, { params: packageGuid ? { package: packageGuid } : {} });
    return response.data;
  },

  /** Alle Theme-Pakete zur Freigabe (nur Rolle 'overlay') */
  getAvailablePackages: async (): Promise<ThemePackageInfo[]> => {
    const response = await apiClient.get('/layout/packages');
    return response.data.packages;
  },

  saveMandantOverlay: async (overlay: ThemeOverlay): Promise<void> => {
    await apiClient.put('/layout/overlay/mandant', { overlay });
  },

  saveMandantSettings: async (settings: Partial<MandantThemeSettings>): Promise<MandantThemeSettings> => {
    const response = await apiClient.put('/layout/settings/mandant', settings);
    return response.data;
  },

  saveUserSettings: async (payload: {
    overlay: ThemeOverlay;
    theme_choice?: string;
    variant_light?: string;
    variant_dark?: string;
    layout_choice?: Record<string, string>;
  }): Promise<void> => {
    await apiClient.put('/layout/settings/user', payload);
  },
};

/** Fehlermeldungen einer abgelehnten Speicherung (422 -> Liste, sonst eine Meldung) */
export function themeSaveErrors(err: any): string[] {
  const detail = err?.response?.data?.detail;
  if (detail && Array.isArray(detail.errors)) return detail.errors.map(String);
  if (typeof detail === 'string') return [detail];
  return [err?.message || 'Speichern fehlgeschlagen'];
}
