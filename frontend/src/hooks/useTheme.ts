/**
 * useTheme Hook V2
 * Component-Based Theming System
 */
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';
import { layoutApi, ActiveThemeResponse } from '../api/layout';

export interface ThemeContextValue {
  currentTheme: ActiveThemeResponse | null;
  themeName: 'light' | 'dark';
  systemTheme: 'light' | 'dark';
  useSystemTheme: boolean;
  isLoading: boolean;
  error: string | null;
  loadTheme: (mode?: 'light' | 'dark') => Promise<void>;
  toggleTheme: () => void;
  setUseSystemTheme: (value: boolean) => void;
}

export const useTheme = (): ThemeContextValue => {
  const { currentMandant } = useAuth();
  const [currentTheme, setCurrentTheme] = useState<ActiveThemeResponse | null>(null);
  const [themeName, setThemeName] = useState<'light' | 'dark'>('light');
  const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>('light');
  const [useSystemTheme, setUseSystemTheme] = useState(false);
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

  // V2 Block Injector
  const injectThemeBlocks = useCallback((themeData: ActiveThemeResponse) => {
    const root = document.documentElement;
    console.log(`🎨 Injecting V2 Theme: ${themeData.theme_variant} (${themeData.mode})`);

    const blocks = themeData.blocks;
    if (!blocks) {
        console.warn("⚠️ No blocks found in theme data!");
        return;
    }

    Object.keys(blocks).forEach(blockName => {
        const block = blocks[blockName];
        
        // Example: blockName="block_header_std"
        // CSS Variable Prefix: --block-header-std
        const prefix = blockName.replace(/_/g, '-');

        Object.keys(block).forEach(prop => {
            const val = block[prop];
            // prop: "bg_color" -> "bg-color"
            const cssProp = prop.replace(/_/g, '-');
            
            const varName = `--${prefix}-${cssProp}`;
            root.style.setProperty(varName, val);
        });
    });

    // Global Mode Class
    if (themeData.mode === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, []);

  // Load Theme
  const loadTheme = useCallback(async (mode?: 'light' | 'dark') => {
    setIsLoading(true);
    setError(null);

    try {
      const modeToLoad = mode || (useSystemTheme ? systemTheme : themeName);
      console.log(`🎨 Loading theme V2 (Mode: ${modeToLoad})...`);
      
      const response = await layoutApi.getActiveTheme(modeToLoad);
      console.log('📦 Theme response:', response);
      
      setCurrentTheme(response);
      setThemeName(response.mode);
      
      // Inject CSS Variables
      injectThemeBlocks(response);

    } catch (err: any) {
      console.error('❌ Failed to load theme V2:', err);
      setError(err.message || 'Failed to load theme');
    } finally {
      setIsLoading(false);
    }
  }, [themeName, systemTheme, useSystemTheme, injectThemeBlocks]);

  // Toggle Theme
  const toggleTheme = useCallback(async () => {
    const newMode = themeName === 'light' ? 'dark' : 'light';
    setThemeName(newMode);
    setUseSystemTheme(false);
    
    // 1. Save Preference
    try {
      await layoutApi.saveThemePreference(newMode);
    } catch (err) {
      console.warn('Could not save preference', err);
    }

    // 2. Reload Theme
    loadTheme(newMode);
  }, [themeName, loadTheme]);

  // Initial Load / Mandant Change
  useEffect(() => {
    if (currentMandant?.uid) {
        // Load default/saved theme
         layoutApi.getThemePreference()
        .then(savedTheme => {
            const mode = (typeof savedTheme === 'string' && savedTheme) ? savedTheme as 'light'|'dark' : 'light';
            setThemeName(mode);
            loadTheme(mode);
        })
        .catch(() => loadTheme('light'));
    }
  }, [currentMandant]); // Reduced dependency to avoid loops

  // System Theme Sync
  useEffect(() => {
    if (useSystemTheme) {
      loadTheme(systemTheme);
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
