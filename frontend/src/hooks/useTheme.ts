/**
 * useTheme Hook
 * Verwaltet Theme-Loading und dynamische CSS-Injection
 */
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';
import { layoutApi } from '../api/layout';

export interface ThemeColors {
  primary: Record<string, string>;
  secondary: Record<string, string>;
  neutral: Record<string, string>;
  success: string;
  warning: string;
  error: string;
  info: string;
  background: {
    primary: string;
    secondary: string;
    tertiary: string;
  };
  text: {
    primary: string;
    secondary: string;
    disabled: string;
    inverse: string;
  };
  border: {
    light: string;
    medium: string;
    dark: string;
  };
}

export interface ThemeTypography {
  fontFamily: {
    primary: string;
    secondary: string;
    mono: string;
  };
  fontSize: Record<string, string | number>;
  fontWeight: Record<string, number>;
  lineHeight: Record<string, number>;
}

export interface Theme {
  mandant_uid: string;
  mandant_name: string;
  theme: 'light' | 'dark';
  colors: ThemeColors;
  typography: ThemeTypography;
  customizations: Record<string, any>;
  assets: Record<string, any>;
}

export interface ThemeContextValue {
  currentTheme: Theme | null;
  themeName: 'light' | 'dark';
  systemTheme: 'light' | 'dark';
  useSystemTheme: boolean;
  isLoading: boolean;
  error: string | null;
  loadTheme: (mandantUid: string, theme?: 'light' | 'dark') => Promise<void>;
  toggleTheme: () => void;
  setUseSystemTheme: (value: boolean) => void;
}

export const useTheme = (): ThemeContextValue => {
  const { currentMandant } = useAuth();
  const [currentTheme, setCurrentTheme] = useState<Theme | null>(null);
  const [themeName, setThemeName] = useState<'light' | 'dark'>('light');
  const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>('light');
  const [useSystemTheme, setUseSystemTheme] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // System Theme Detection
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    const updateSystemTheme = (e: MediaQueryListEvent | MediaQueryList) => {
      setSystemTheme(e.matches ? 'dark' : 'light');
    };

    updateSystemTheme(mediaQuery);
    mediaQuery.addEventListener('change', updateSystemTheme);

    return () => mediaQuery.removeEventListener('change', updateSystemTheme);
  }, []);

  // CSS Injection
  const injectThemeCSS = useCallback((theme: Theme) => {
    const root = document.documentElement;
    
    console.log('🎨 Injecting theme:', theme.mandant_name, theme.theme);
    console.log('Primary colors:', theme.colors.primary);
    
    // Set data attributes
    root.setAttribute('data-theme', theme.theme);
    root.setAttribute('data-mandant', theme.mandant_uid);

    // Inject colors
    const injectColorScale = (prefix: string, colors: Record<string, any>) => {
      Object.entries(colors).forEach(([subKey, value]) => {
        if (typeof value === 'object' && value !== null) {
          // Nested object (e.g., primary.500)
          Object.entries(value).forEach(([nestedKey, nestedValue]) => {
            const varName = `--color-${prefix}-${nestedKey}`;
            root.style.setProperty(varName, nestedValue as string);
            console.log(`  ${varName}: ${nestedValue}`);
          });
        } else {
          // Flat value
          const varName = `--color-${prefix}-${subKey}`;
          root.style.setProperty(varName, value as string);
          console.log(`  ${varName}: ${value}`);
        }
      });
    };

    injectColorScale('primary', theme.colors.primary);
    injectColorScale('secondary', theme.colors.secondary);
    injectColorScale('neutral', theme.colors.neutral);
    
    root.style.setProperty('--color-success', theme.colors.success);
    root.style.setProperty('--color-warning', theme.colors.warning);
    root.style.setProperty('--color-error', theme.colors.error);
    root.style.setProperty('--color-info', theme.colors.info);

    injectColorScale('background', theme.colors.background);
    injectColorScale('text', theme.colors.text);
    injectColorScale('border', theme.colors.border);

    // Inject typography
    root.style.setProperty('--font-primary', theme.typography.fontFamily.primary);
    root.style.setProperty('--font-secondary', theme.typography.fontFamily.secondary);
    root.style.setProperty('--font-mono', theme.typography.fontFamily.mono);

    const fontScale = theme.typography.fontSize.scale as number || 1.0;
    root.style.setProperty('--font-scale', fontScale.toString());

    // Inject customizations
    if (theme.customizations?.borderRadius) {
      Object.entries(theme.customizations.borderRadius).forEach(([key, value]) => {
        root.style.setProperty(`--border-radius-${key}`, value as string);
      });
    }

    console.log(`✅ Theme injected: ${theme.mandant_name} (${theme.theme})`);
  }, []);

  // Load Theme
  const loadTheme = useCallback(async (mandantUid: string, theme?: 'light' | 'dark') => {
    setIsLoading(true);
    setError(null);

    try {
      const themeToLoad = theme || (useSystemTheme ? systemTheme : themeName);
      console.log(`🎨 Loading theme: ${mandantUid} → ${themeToLoad}`);
      
      const response = await layoutApi.getMandantTheme(mandantUid, themeToLoad);
      console.log('📦 Theme response:', response);
      
      // Backend gibt direkt die Theme-Daten zurück, nicht verschachtelt
      const themeData: Theme = {
        mandant_uid: response.mandant_uid,
        mandant_name: response.mandant_name,
        theme: response.theme,
        colors: response.colors as any,
        typography: response.typography as any,
        customizations: response.customizations,
        assets: response.assets,
      };

      console.log('✅ Theme data prepared:', themeData.mandant_name, themeData.theme);
      setCurrentTheme(themeData);
      setThemeName(themeData.theme);
      injectThemeCSS(themeData);
    } catch (err: any) {
      console.error('❌ Failed to load theme:', err);
      setError(err.message || 'Failed to load theme');
    } finally {
      setIsLoading(false);
    }
  }, [themeName, systemTheme, useSystemTheme, injectThemeCSS]);

  // Toggle Theme
  const toggleTheme = useCallback(async () => {
    if (!currentTheme) return;

    const newTheme = themeName === 'light' ? 'dark' : 'light';
    setThemeName(newTheme);
    setUseSystemTheme(false);
    
    // Speichere Präferenz in Backend
    try {
      await layoutApi.saveThemePreference(newTheme);
      console.log(`✅ Theme-Präferenz gespeichert: ${newTheme}`);
    } catch (err) {
      console.error('⚠️ Fehler beim Speichern der Theme-Präferenz:', err);
    }
    
    // Lade neues Theme
    loadTheme(currentTheme.mandant_uid, newTheme);
  }, [currentTheme, themeName, loadTheme]);

  // Auto-load theme when mandant changes
  useEffect(() => {
    if (currentMandant?.uid) {
      console.log('🔍 Loading theme for mandant:', currentMandant.uid, currentMandant.name);
      
      // Lade gespeicherte Theme-Präferenz
      layoutApi.getThemePreference()
        .then(savedTheme => {
          console.log('💾 Gespeicherte Theme-Präferenz (type:', typeof savedTheme, '):', savedTheme);
          
          // Sicherstellen dass savedTheme ein String ist
          const themeString = typeof savedTheme === 'string' ? savedTheme : 'light';
          setThemeName(themeString as 'light' | 'dark');
          return loadTheme(currentMandant.uid, themeString as 'light' | 'dark');
        })
        .catch(err => {
          console.error('❌ Failed to load theme preference, using default:', err);
          return loadTheme(currentMandant.uid, 'light');
        });
    }
  }, [currentMandant]);

  // Update theme when system theme changes (if useSystemTheme is true)
  useEffect(() => {
    if (useSystemTheme && currentTheme) {
      loadTheme(currentTheme.mandant_uid, systemTheme);
    }
  }, [systemTheme, useSystemTheme]);

  return {
    currentTheme,
    themeName,
    systemTheme,
    useSystemTheme,
    isLoading,
    error,
    loadTheme,
    toggleTheme,
    setUseSystemTheme,
  };
};
