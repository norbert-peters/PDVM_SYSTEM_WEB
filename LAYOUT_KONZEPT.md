# PDVM System Web - Layout-Konzept

**Erstellt:** 3. Januar 2026  
**Version:** 1.0  
**Umsetzungsstrategie:** Linear von groß nach klein (Desktop-First → Mobile)

---

## 1. Übersicht

Das Layout-System basiert auf einer **3-Schichten-Architektur**:

1. **Zentrale Layouts** (auth.sys_central_layout) - Für alle Mandanten gleich
2. **Mandanten-Themes** (pdvm_system.sys_layout) - Mandantenspezifische Anpassungen
3. **Responsive Breakpoints** - 4 Geräteklassen

---

## 2. Datenbank-Struktur

### 2.1 Tabelle: auth.sys_central_layout

Zentrale Layout-Vorlagen für alle Mandanten.

```sql
CREATE TABLE IF NOT EXISTS auth.sys_central_layout (
    layout_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layout_name VARCHAR(100) NOT NULL UNIQUE,
    layout_type VARCHAR(50) NOT NULL, -- 'login', 'mandant_select', 'dashboard_base'
    layout_config JSONB NOT NULL,
    version VARCHAR(20) DEFAULT '1.0',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Beispiel für layout_config:
{
    "structure": {
        "header_height": "64px",
        "sidebar_width": "240px",
        "sidebar_collapsed_width": "60px",
        "footer_height": "48px"
    },
    "grid": {
        "columns": 12,
        "gutter": "16px"
    },
    "responsive": {
        "breakpoints": {
            "mobile": "640px",
            "tablet": "1024px",
            "laptop": "1440px",
            "monitor": "1920px"
        }
    }
}
```

### 2.2 Tabelle: pdvm_system.sys_layout

Mandantenspezifische Themes und Anpassungen.

```sql
CREATE TABLE IF NOT EXISTS sys_layout (
    layout_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mandant_guid UUID NOT NULL,
    theme_name VARCHAR(100) NOT NULL, -- 'light', 'dark'
    
    -- Farbschema
    colors JSONB NOT NULL,
    
    -- Typografie
    typography JSONB NOT NULL,
    
    -- Zusätzliche Anpassungen
    customizations JSONB,
    
    -- Logos und Grafiken
    assets JSONB,
    
    -- Metadaten
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID,
    
    UNIQUE(mandant_guid, theme_name)
);

-- Beispiel für colors (Light Theme):
{
    "primary": {
        "50": "#e3f2fd",
        "100": "#bbdefb",
        "500": "#2196f3",
        "700": "#1976d2",
        "900": "#0d47a1"
    },
    "secondary": {
        "50": "#f3e5f5",
        "500": "#9c27b0",
        "900": "#4a148c"
    },
    "neutral": {
        "50": "#fafafa",
        "100": "#f5f5f5",
        "200": "#eeeeee",
        "500": "#9e9e9e",
        "700": "#616161",
        "900": "#212121"
    },
    "success": "#4caf50",
    "warning": "#ff9800",
    "error": "#f44336",
    "info": "#2196f3",
    "background": {
        "primary": "#ffffff",
        "secondary": "#f5f5f5",
        "tertiary": "#eeeeee"
    },
    "text": {
        "primary": "#212121",
        "secondary": "#757575",
        "disabled": "#bdbdbd"
    },
    "border": {
        "light": "#e0e0e0",
        "medium": "#bdbdbd",
        "dark": "#757575"
    }
}

-- Beispiel für typography:
{
    "fontFamily": {
        "primary": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "secondary": "'Roboto', sans-serif",
        "mono": "'Fira Code', 'Courier New', monospace"
    },
    "fontSize": {
        "scale": 1.0,  -- Skalierungsfaktor zur Systemschrift
        "base": "16px",
        "xs": "0.75rem",
        "sm": "0.875rem",
        "md": "1rem",
        "lg": "1.125rem",
        "xl": "1.25rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem"
    },
    "fontWeight": {
        "light": 300,
        "normal": 400,
        "medium": 500,
        "semibold": 600,
        "bold": 700
    },
    "lineHeight": {
        "tight": 1.25,
        "normal": 1.5,
        "relaxed": 1.75
    }
}

-- Beispiel für customizations:
{
    "animations": {
        "enabled": true,
        "duration": "200ms",
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)"
    },
    "shadows": {
        "enabled": true,
        "intensity": "medium"
    },
    "borderRadius": {
        "sm": "4px",
        "md": "8px",
        "lg": "12px",
        "full": "9999px"
    }
}

-- Beispiel für assets:
{
    "logo": {
        "light": "/assets/mandant_1/logo_light.svg",
        "dark": "/assets/mandant_1/logo_dark.svg",
        "favicon": "/assets/mandant_1/favicon.ico"
    },
    "icons": {
        "custom": "/assets/mandant_1/icons/"
    },
    "backgrounds": {
        "login": "/assets/mandant_1/bg_login.jpg",
        "dashboard": "/assets/mandant_1/bg_dashboard.jpg"
    }
}
```

---

## 3. Layout-Struktur (Desktop/Monitor)

### 3.1 Hauptlayout-Bereiche

```
┌─────────────────────────────────────────────────────────────┐
│  Header (64px)                                               │
│  ┌──────────────────┬────────────────────────────────────┐  │
│  │ Logo + App-Name  │  Stichtagsbar │ User-Info │ Theme │  │
│  └──────────────────┴────────────────────────────────────┘  │
├──────────┬──────────────────────────────────────────────────┤
│          │  Horizontales Hauptmenü (48px)                   │
│          │  ┌────┬────┬────┬────┬────┬────────────────┐    │
│          │  │Tab1│Tab2│Tab3│Tab4│... │ Zusatzmenü    │    │
│          │  └────┴────┴────┴────┴────┴────────────────┘    │
│ Sidebar  ├──────────────────────────────────────────────────┤
│ (240px)  │  Content-Bereich                                 │
│          │                                                   │
│ Vertikal │  ┌────────────────────────────────────────────┐  │
│ Menü     │  │                                            │  │
│          │  │  Dynamischer Arbeitsbereich                │  │
│          │  │                                            │  │
│ ├─ Item1 │  │  (Formulare, Tabellen, Dashboards, etc.)   │  │
│ ├─ Item2 │  │                                            │  │
│ ├─ Item3 │  │                                            │  │
│ └─ Item4 │  │                                            │  │
│          │  └────────────────────────────────────────────┘  │
│ (Toggle) │                                                   │
└──────────┴───────────────────────────────────────────────────┘
```

### 3.2 Komponenten-Hierarchie

```
<AppLayout>
  ├─ <Header>
  │   ├─ <Logo />
  │   ├─ <AppTitle />
  │   ├─ <StichtagsBar />
  │   ├─ <UserMenu />
  │   └─ <ThemeToggle />
  │
  ├─ <MainContainer>
  │   ├─ <Sidebar>
  │   │   ├─ <VerticalNav />
  │   │   └─ <SidebarToggle />
  │   │
  │   └─ <MainContent>
  │       ├─ <HorizontalNav>
  │       │   ├─ <TabMenu />
  │       │   └─ <AdditionalMenu />
  │       │
  │       └─ <ContentArea>
  │           └─ {children}
  │
  └─ <Footer /> (optional)
```

---

## 4. Responsive Breakpoints (4 Stufen)

### 4.1 Monitor/Beamer (≥1920px)

- **Sidebar:** 240px breit, immer sichtbar
- **Horizontal Menu:** Alle Tabs sichtbar
- **Content:** Maximale Breite mit Padding
- **Grid:** 12 Spalten, 24px Gutter

### 4.2 Laptop (1440px - 1919px)

- **Sidebar:** 200px breit, immer sichtbar
- **Horizontal Menu:** Alle wichtigen Tabs, Rest im Dropdown
- **Content:** Volle Breite mit 16px Padding
- **Grid:** 12 Spalten, 16px Gutter

### 4.3 Tablet (1024px - 1439px)

- **Sidebar:** Kollabiert (60px Icons), expandierbar als Overlay
- **Horizontal Menu:** Wichtigste Tabs, Rest im Burger-Menu
- **Content:** Volle Breite mit 12px Padding
- **Grid:** 8 Spalten, 12px Gutter

### 4.4 Handy (< 1024px)

- **Sidebar:** Komplett versteckt, Drawer von links
- **Horizontal Menu:** Burger-Menu (Hamburger-Icon)
- **Content:** Volle Breite, Stack-Layout
- **Grid:** 4 Spalten, 8px Gutter
- **Header:** Reduziert (nur Logo, Burger, User)

---

## 5. CSS-Architektur

### 5.1 CSS Custom Properties (CSS Variables)

```css
:root {
    /* Dynamisch aus Datenbank geladen */
    
    /* Layout-Dimensionen */
    --header-height: 64px;
    --sidebar-width: 240px;
    --sidebar-collapsed: 60px;
    --horizontal-menu-height: 48px;
    --footer-height: 48px;
    
    /* Breakpoints */
    --bp-mobile: 640px;
    --bp-tablet: 1024px;
    --bp-laptop: 1440px;
    --bp-monitor: 1920px;
    
    /* Spacing */
    --spacing-xs: 4px;
    --spacing-sm: 8px;
    --spacing-md: 16px;
    --spacing-lg: 24px;
    --spacing-xl: 32px;
    
    /* Z-Index-Ebenen */
    --z-dropdown: 1000;
    --z-sticky: 1020;
    --z-fixed: 1030;
    --z-modal-backdrop: 1040;
    --z-modal: 1050;
    --z-popover: 1060;
    --z-tooltip: 1070;
}

/* Mandantenspezifische Farben (werden dynamisch injiziert) */
:root[data-theme="light"][data-mandant="mandant_1"] {
    --color-primary: #2196f3;
    --color-primary-hover: #1976d2;
    --color-secondary: #9c27b0;
    --color-background: #ffffff;
    --color-surface: #f5f5f5;
    --color-text-primary: #212121;
    --color-text-secondary: #757575;
    --color-border: #e0e0e0;
    /* ... weitere Farben */
}

:root[data-theme="dark"][data-mandant="mandant_1"] {
    --color-primary: #42a5f5;
    --color-primary-hover: #1e88e5;
    --color-secondary: #ab47bc;
    --color-background: #121212;
    --color-surface: #1e1e1e;
    --color-text-primary: #ffffff;
    --color-text-secondary: #b0b0b0;
    --color-border: #333333;
    /* ... weitere Farben */
}
```

### 5.2 Ordnerstruktur

```
frontend/
├─ src/
│  ├─ styles/
│  │  ├─ base/
│  │  │  ├─ reset.css
│  │  │  ├─ typography.css
│  │  │  └─ variables.css
│  │  ├─ layouts/
│  │  │  ├─ app-layout.css
│  │  │  ├─ header.css
│  │  │  ├─ sidebar.css
│  │  │  ├─ content.css
│  │  │  └─ responsive.css
│  │  ├─ components/
│  │  │  ├─ buttons.css
│  │  │  ├─ forms.css
│  │  │  ├─ cards.css
│  │  │  └─ ...
│  │  └─ themes/
│  │     ├─ theme-loader.ts
│  │     └─ theme-utils.ts
│  │
│  ├─ components/
│  │  ├─ layout/
│  │  │  ├─ AppLayout.tsx
│  │  │  ├─ Header.tsx
│  │  │  ├─ Sidebar.tsx
│  │  │  ├─ HorizontalNav.tsx
│  │  │  ├─ ContentArea.tsx
│  │  │  └─ StichtagsBar.tsx
│  │  └─ ...
│  │
│  └─ hooks/
│     ├─ useTheme.ts
│     ├─ useLayout.ts
│     └─ useResponsive.ts
```

---

## 6. Implementierungsplan (Linear)

### Phase 1: Grundgerüst (Desktop/Monitor) ✓ START HIER

**Schritt 1.1: Datenbank-Setup**
- [ ] SQL-Schema für `auth.sys_central_layout` erstellen
- [ ] SQL-Schema für `pdvm_system.sys_layout` erstellen
- [ ] Basis-Layout-Konfiguration einfügen
- [ ] 2 Test-Mandanten mit unterschiedlichen Themes erstellen

**Schritt 1.2: CSS-Grundstruktur**
- [ ] CSS Reset und Base-Styles
- [ ] CSS Custom Properties definieren
- [ ] Layout-Grid-System (12-Spalten)
- [ ] Utility-Klassen für Spacing, Farben, etc.

**Schritt 1.3: Layout-Komponenten (Desktop)**
- [ ] `AppLayout.tsx` - Haupt-Container
- [ ] `Header.tsx` - Header mit Logo, Stichtagsbar, User-Menu
- [ ] `Sidebar.tsx` - Vertikales Menü mit Toggle
- [ ] `HorizontalNav.tsx` - Tab-Menü mit Zusatzmenü
- [ ] `ContentArea.tsx` - Arbeitsbereich

**Schritt 1.4: Theme-System**
- [ ] Theme-Loader (lädt Mandanten-Theme aus DB)
- [ ] Theme-Context (React Context für Theme-State)
- [ ] `useTheme` Hook
- [ ] Theme-Toggle Komponente (Hell/Dunkel)
- [ ] CSS-Injection für dynamische Farben

**Schritt 1.5: API-Integration**
- [ ] Backend-Endpoint: `GET /api/layout/central/{layout_type}`
- [ ] Backend-Endpoint: `GET /api/layout/mandant/{mandant_guid}/{theme}`
- [ ] Backend-Endpoint: `PUT /api/layout/mandant/{mandant_guid}/{theme}`
- [ ] Frontend API-Client für Layout-Daten

### Phase 2: Responsive Design (Laptop → Tablet → Handy)

**Schritt 2.1: Laptop (1440px - 1919px)**
- [ ] Media Queries für Laptop-Ansicht
- [ ] Sidebar-Breite anpassen
- [ ] Horizontal-Menu Overflow-Handling

**Schritt 2.2: Tablet (1024px - 1439px)**
- [ ] Sidebar Collapse/Expand Funktionalität
- [ ] Horizontal-Menu als Dropdown
- [ ] Touch-Gesten für Sidebar

**Schritt 2.3: Handy (< 1024px)**
- [ ] Mobile Header mit Burger-Menu
- [ ] Sidebar als Drawer
- [ ] Stack-Layout für Content
- [ ] Mobile Navigation

### Phase 3: Mandanten-spezifische Features

**Schritt 3.1: Mandant 1 (z.B. Blau-Theme)**
- [ ] Farbschema definieren (Hell/Dunkel)
- [ ] Logo und Assets hochladen
- [ ] Typografie anpassen
- [ ] Testen

**Schritt 3.2: Mandant 2 (z.B. Grün-Theme)**
- [ ] Anderes Farbschema (Hell/Dunkel)
- [ ] Andere Schriftart
- [ ] Unterschiedliche Border-Radius
- [ ] Testen und Vergleichen

### Phase 4: Erweiterte Features

**Schritt 4.1: Stichtagsbar**
- [ ] Komponente mit Datumswähler
- [ ] State-Management (Global/Context)
- [ ] Persistierung

**Schritt 4.2: User-Einstellungen**
- [ ] Präferenz-Speicherung (Theme, Sidebar-Zustand, etc.)
- [ ] User-spezifische Overrides
- [ ] Settings-Panel

**Schritt 4.3: Grafik-Elemente**
- [ ] Logo-Upload und Verwaltung
- [ ] Icon-System (Custom Icons pro Mandant)
- [ ] Background-Images

### Phase 5: Optimierung & Testing

- [ ] Performance-Optimierung
- [ ] Cross-Browser-Testing
- [ ] Accessibility (ARIA, Keyboard-Navigation)
- [ ] Dokumentation

---

## 7. Beispiel-Komponenten

### 7.1 AppLayout.tsx

```typescript
import React, { useEffect } from 'react';
import { useTheme } from '../hooks/useTheme';
import { useAuth } from '../hooks/useAuth';
import Header from './Header';
import Sidebar from './Sidebar';
import HorizontalNav from './HorizontalNav';
import ContentArea from './ContentArea';

interface AppLayoutProps {
    children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
    const { currentTheme, loadMandantTheme } = useTheme();
    const { currentUser, currentMandant } = useAuth();
    const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);

    useEffect(() => {
        if (currentMandant) {
            loadMandantTheme(currentMandant.mandant_guid);
        }
    }, [currentMandant]);

    // CSS-Variablen dynamisch setzen
    useEffect(() => {
        if (currentTheme) {
            const root = document.documentElement;
            root.setAttribute('data-theme', currentTheme.theme_name);
            root.setAttribute('data-mandant', currentMandant?.mandant_guid || '');
            
            // Farben injizieren
            Object.entries(currentTheme.colors).forEach(([key, value]) => {
                if (typeof value === 'object') {
                    Object.entries(value).forEach(([subKey, subValue]) => {
                        root.style.setProperty(`--color-${key}-${subKey}`, subValue as string);
                    });
                } else {
                    root.style.setProperty(`--color-${key}`, value as string);
                }
            });
            
            // Typografie injizieren
            const { fontFamily, fontSize } = currentTheme.typography;
            root.style.setProperty('--font-primary', fontFamily.primary);
            root.style.setProperty('--font-scale', fontSize.scale.toString());
        }
    }, [currentTheme]);

    return (
        <div className="app-layout">
            <Header />
            <div className="main-container">
                <Sidebar 
                    collapsed={sidebarCollapsed}
                    onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
                />
                <div className="main-content">
                    <HorizontalNav />
                    <ContentArea>
                        {children}
                    </ContentArea>
                </div>
            </div>
        </div>
    );
};
```

### 7.2 useTheme Hook

```typescript
import { useState, useEffect } from 'react';
import { api } from '../api/client';

interface Theme {
    layout_id: string;
    mandant_guid: string;
    theme_name: 'light' | 'dark';
    colors: Record<string, any>;
    typography: Record<string, any>;
    customizations: Record<string, any>;
    assets: Record<string, any>;
}

export const useTheme = () => {
    const [currentTheme, setCurrentTheme] = useState<Theme | null>(null);
    const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>('light');
    const [useSystemTheme, setUseSystemTheme] = useState(true);

    // System-Theme detection
    useEffect(() => {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        setSystemTheme(mediaQuery.matches ? 'dark' : 'light');

        const handler = (e: MediaQueryListEvent) => {
            setSystemTheme(e.matches ? 'dark' : 'light');
        };

        mediaQuery.addEventListener('change', handler);
        return () => mediaQuery.removeEventListener('change', handler);
    }, []);

    const loadMandantTheme = async (mandantGuid: string) => {
        try {
            const themeName = useSystemTheme ? systemTheme : 'light';
            const response = await api.get(`/layout/mandant/${mandantGuid}/${themeName}`);
            setCurrentTheme(response.data);
        } catch (error) {
            console.error('Failed to load mandant theme:', error);
        }
    };

    const toggleTheme = () => {
        if (currentTheme) {
            const newThemeName = currentTheme.theme_name === 'light' ? 'dark' : 'light';
            loadMandantTheme(currentTheme.mandant_guid);
            setUseSystemTheme(false);
        }
    };

    return {
        currentTheme,
        systemTheme,
        useSystemTheme,
        setUseSystemTheme,
        loadMandantTheme,
        toggleTheme
    };
};
```

---

## 8. Test-Mandanten Konfiguration

### Mandant 1: "TechCorp" (Blau-Theme)

**Light Mode:**
- Primary: #2196f3 (Blau)
- Secondary: #ff9800 (Orange)
- Background: #ffffff
- Font: Inter, Sans-Serif
- Font Scale: 1.0

**Dark Mode:**
- Primary: #42a5f5 (Hell-Blau)
- Secondary: #ffb74d (Hell-Orange)
- Background: #121212
- Font: Inter, Sans-Serif
- Font Scale: 1.0

### Mandant 2: "GreenSolutions" (Grün-Theme)

**Light Mode:**
- Primary: #4caf50 (Grün)
- Secondary: #9c27b0 (Lila)
- Background: #fafafa
- Font: Roboto, Sans-Serif
- Font Scale: 1.1

**Dark Mode:**
- Primary: #66bb6a (Hell-Grün)
- Secondary: #ba68c8 (Hell-Lila)
- Background: #1a1a1a
- Font: Roboto, Sans-Serif
- Font Scale: 1.1

---

## 9. Checkliste für Umsetzung

### Phase 1: Foundation (Woche 1-2)
- [ ] Datenbank-Tabellen erstellen
- [ ] Basis-CSS-Struktur
- [ ] Layout-Komponenten (Desktop)
- [ ] Theme-System implementieren
- [ ] 2 Test-Mandanten anlegen

### Phase 2: Responsive (Woche 3)
- [ ] Laptop-Ansicht
- [ ] Tablet-Ansicht
- [ ] Mobile-Ansicht
- [ ] Testing auf verschiedenen Geräten

### Phase 3: Features (Woche 4)
- [ ] Stichtagsbar
- [ ] User-Settings
- [ ] Grafik-Upload
- [ ] Mandanten-Switch testen

### Phase 4: Polishing (Woche 5)
- [ ] Performance
- [ ] Accessibility
- [ ] Browser-Kompatibilität
- [ ] Dokumentation

---

## 10. Nächste Schritte

1. **JETZT STARTEN:** Datenbank-Schema erstellen und Test-Daten einfügen
2. CSS-Grundstruktur aufbauen
3. Erste Layout-Komponente (AppLayout) implementieren
4. Theme-Loader entwickeln
5. Test mit zwei Mandanten

---

## 11. Offene Fragen

- [ ] Sollen Login/Mandantenauswahl wirklich in auth.sys_central_layout oder separates System?
- [ ] Welche konkreten Grafik-Elemente sollen mandantenspezifisch sein?
- [ ] Brauchen wir einen Layout-Editor für Administratoren?
- [ ] Soll die Sidebar-Position (links/rechts) konfigurierbar sein?
- [ ] Animations/Transitions global oder pro Mandant?

---

**Status:** Konzept erstellt, bereit für Phase 1 Implementation
