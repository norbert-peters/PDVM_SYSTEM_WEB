/**
 * Theme API - Lädt Farbschema aus Backend
 */

import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export interface ThemeColors {
  theme_guid: string;
  colors: {
    [gruppe: string]: {
      [feld: string]: string;
    };
  };
}

/**
 * Lädt Theme-Farben aus Backend (GCS)
 */
export async function loadThemeColors(): Promise<ThemeColors> {
  const token = localStorage.getItem('token');
  
  const response = await axios.get(`${API_BASE_URL}/gcs/theme`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });
  
  return response.data;
}

/**
 * Setzt CSS-Variablen aus Theme-Farben
 * 
 * Erwartet Gruppen wie:
 * - BACKGROUND: { PRIMARY, SECONDARY, TERTIARY }
 * - TEXT: { PRIMARY, SECONDARY, DISABLED }
 * - PRIMARY: { DEFAULT, HOVER, ACTIVE }
 * etc.
 */
export function applyCSSVariables(colors: ThemeColors['colors']) {
  const root = document.documentElement;
  
  // BACKGROUND-Farben
  if (colors.BACKGROUND) {
    if (colors.BACKGROUND.PRIMARY) root.style.setProperty('--color-background-primary', colors.BACKGROUND.PRIMARY);
    if (colors.BACKGROUND.SECONDARY) root.style.setProperty('--color-background-secondary', colors.BACKGROUND.SECONDARY);
    if (colors.BACKGROUND.TERTIARY) root.style.setProperty('--color-background-tertiary', colors.BACKGROUND.TERTIARY);
  }
  
  // TEXT-Farben
  if (colors.TEXT) {
    if (colors.TEXT.PRIMARY) root.style.setProperty('--color-text-primary', colors.TEXT.PRIMARY);
    if (colors.TEXT.SECONDARY) root.style.setProperty('--color-text-secondary', colors.TEXT.SECONDARY);
    if (colors.TEXT.DISABLED) root.style.setProperty('--color-text-disabled', colors.TEXT.DISABLED);
  }
  
  // PRIMARY-Farben
  if (colors.PRIMARY) {
    if (colors.PRIMARY.DEFAULT) root.style.setProperty('--color-primary', colors.PRIMARY.DEFAULT);
    if (colors.PRIMARY.HOVER) root.style.setProperty('--color-primary-hover', colors.PRIMARY.HOVER);
    if (colors.PRIMARY.ACTIVE) root.style.setProperty('--color-primary-active', colors.PRIMARY.ACTIVE);
  }
  
  // BORDER-Farben
  if (colors.BORDER) {
    if (colors.BORDER.DEFAULT) root.style.setProperty('--border-color', colors.BORDER.DEFAULT);
  }
  
  // SURFACE-Farben (für Cards, Dialoge, Dropdowns)
  if (colors.SURFACE) {
    if (colors.SURFACE.PRIMARY) root.style.setProperty('--surface-primary', colors.SURFACE.PRIMARY);
    if (colors.SURFACE.SECONDARY) root.style.setProperty('--surface-secondary', colors.SURFACE.SECONDARY);
    if (colors.SURFACE.HOVER) root.style.setProperty('--surface-hover', colors.SURFACE.HOVER);
  }
}
