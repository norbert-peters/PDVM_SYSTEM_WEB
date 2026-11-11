/**
 * ThemeContext - einzige Quelle fuer das aktive Theme (ARCHITECTURE_RULES 2.1)
 *
 * Laedt das serverseitig aufgeloeste Theme (GET /api/layout/resolved), setzt die CSS-Variablen auf :root
 * und haelt je Mandant und Modus einen localStorage-Cache, damit nach dem Laden/Umschalten nichts flackert.
 */
import React, { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import { layoutApi, type ResolvedThemeResponse, type ThemeMode } from '../api/layout';
import { themeTokensToCssVars } from '../utils/themeVars';
import { applyLayoutAttributes } from '../utils/layoutAttributes';

export interface ThemeContextValue {
  currentTheme: ResolvedThemeResponse | null;
  themeName: ThemeMode;
  isLoading: boolean;
  error: string | null;
  toggleTheme: () => void;
  setThemeMode: (mode: ThemeMode) => void;
  reloadTheme: () => Promise<void>;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const LAST_MODE_KEY = 'pdvm_theme_mode';
const cacheKey = (mandantUid: string, mode: ThemeMode) => `pdvm_theme:${mandantUid}:${mode}`;

function readCache(mandantUid: string, mode: ThemeMode): ResolvedThemeResponse | null {
  try {
    const raw = localStorage.getItem(cacheKey(mandantUid, mode));
    return raw ? (JSON.parse(raw) as ResolvedThemeResponse) : null;
  } catch {
    return null;
  }
}

function writeCache(mandantUid: string, theme: ResolvedThemeResponse) {
  try {
    localStorage.setItem(cacheKey(mandantUid, theme.mode), JSON.stringify(theme));
    localStorage.setItem(LAST_MODE_KEY, theme.mode);
  } catch {
    // Cache ist optional
  }
}

function readLastMode(): ThemeMode {
  return localStorage.getItem(LAST_MODE_KEY) === 'dark' ? 'dark' : 'light';
}

/** Setzt die Tokens als CSS-Variablen (--<gruppe>-<token>) und gibt die gesetzten Namen zurueck. */
function applyTheme(theme: ResolvedThemeResponse, previouslyApplied: Set<string>): Set<string> {
  const root = document.documentElement;
  const vars = themeTokensToCssVars(theme.blocks);
  const applied = new Set<string>(Object.keys(vars));

  Object.entries(vars).forEach(([name, value]) => root.style.setProperty(name, value));

  // Tokens der vorherigen Variante, die in der neuen nicht mehr vorkommen, nicht stehen lassen
  previouslyApplied.forEach((name) => {
    if (!applied.has(name)) root.style.removeProperty(name);
  });

  root.dataset.theme = theme.mode;
  root.classList.toggle('dark', theme.mode === 'dark');
  applyLayoutAttributes(theme.layout);
  return applied;
}

function clearTheme(applied: Set<string>) {
  const root = document.documentElement;
  applied.forEach((name) => root.style.removeProperty(name));
  delete root.dataset.theme;
  root.classList.remove('dark');
  applyLayoutAttributes(null);
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { mandantId } = useAuth();
  const [currentTheme, setCurrentTheme] = useState<ResolvedThemeResponse | null>(null);
  const [themeName, setThemeName] = useState<ThemeMode>(readLastMode);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const requestRef = useRef(0);

  const show = useCallback((theme: ResolvedThemeResponse) => {
    appliedRef.current = applyTheme(theme, appliedRef.current);
    setCurrentTheme(theme);
    setThemeName(theme.mode);
  }, []);

  // mode=undefined -> gespeicherte Benutzer-Praeferenz des Servers
  const load = useCallback(async (mode?: ThemeMode) => {
    if (!mandantId) return;
    const requestId = ++requestRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const theme = await layoutApi.getResolvedTheme(mode);
      if (requestId !== requestRef.current) return; // veraltete Antwort
      show(theme);
      writeCache(mandantId, theme);
      theme.contrast_issues?.forEach((c) =>
        console.warn(`Theme-Kontrast ${c.fg} auf ${c.bg}: ${c.ratio} < ${c.min}`)
      );
    } catch (err: any) {
      if (requestId !== requestRef.current) return;
      console.error('Theme konnte nicht geladen werden:', err);
      setError(err?.message || 'Theme konnte nicht geladen werden');
    } finally {
      if (requestId === requestRef.current) setIsLoading(false);
    }
  }, [mandantId, show]);

  // Mandantenwechsel: Cache sofort anwenden (vor dem ersten Paint), danach vom Server aktualisieren
  useLayoutEffect(() => {
    if (!mandantId) return;
    const cached = readCache(mandantId, readLastMode());
    if (cached) show(cached);
  }, [mandantId, show]);

  useEffect(() => {
    void load();
  }, [load]);

  // Beim Verlassen (Logout) die Mandanten-Variablen entfernen
  useEffect(() => () => clearTheme(appliedRef.current), []);

  const setThemeMode = useCallback((mode: ThemeMode) => {
    if (!mandantId) return;
    const cached = readCache(mandantId, mode);
    if (cached) show(cached); // sofort umschalten, der Server liefert danach den aktuellen Stand
    else setThemeName(mode);
    void layoutApi.saveThemePreference(mode).catch((err) => console.warn('Theme-Praeferenz nicht gespeichert', err));
    void load(mode);
  }, [mandantId, show, load]);

  const toggleTheme = useCallback(() => {
    setThemeMode(themeName === 'light' ? 'dark' : 'light');
  }, [themeName, setThemeMode]);

  const value = useMemo<ThemeContextValue>(() => ({
    currentTheme,
    themeName,
    isLoading,
    error,
    toggleTheme,
    setThemeMode,
    reloadTheme: () => load(themeName),
  }), [currentTheme, themeName, isLoading, error, toggleTheme, setThemeMode, load]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = (): ThemeContextValue => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
