-- ============================================================================
-- PDVM System Web - Layout Management Schema
-- Created: 2026-01-04
-- Database: pdvm_system
-- Description: Zentrale und mandantenspezifische Layout-Konfigurationen
-- ============================================================================

-- Tabelle für zentrale Layout-Vorlagen (für alle Mandanten gleich)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sys_central_layout (
    layout_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layout_name VARCHAR(100) NOT NULL UNIQUE,
    layout_type VARCHAR(50) NOT NULL CHECK (layout_type IN ('login', 'mandant_select', 'dashboard_base')),
    layout_config JSONB NOT NULL,
    version VARCHAR(20) DEFAULT '1.0',
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID
);

-- Index für schnellen Zugriff nach Typ
CREATE INDEX IF NOT EXISTS idx_central_layout_type ON sys_central_layout(layout_type);
CREATE INDEX IF NOT EXISTS idx_central_layout_active ON sys_central_layout(is_active);

-- Kommentare
COMMENT ON TABLE sys_central_layout IS 'Zentrale Layout-Vorlagen für alle Mandanten';
COMMENT ON COLUMN sys_central_layout.layout_type IS 'Typ: login, mandant_select, dashboard_base';
COMMENT ON COLUMN sys_central_layout.layout_config IS 'JSON: structure, grid, responsive breakpoints';


-- Tabelle für mandantenspezifische Themes und Layouts
-- ============================================================================
CREATE TABLE IF NOT EXISTS sys_layout (
    layout_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mandant_guid UUID NOT NULL,
    theme_name VARCHAR(100) NOT NULL CHECK (theme_name IN ('light', 'dark')),
    
    -- Farbschema (JSONB für flexible Farbpaletten)
    colors JSONB NOT NULL,
    
    -- Typografie-Einstellungen
    typography JSONB NOT NULL,
    
    -- Zusätzliche Anpassungen
    customizations JSONB,
    
    -- Logos und Grafiken
    assets JSONB,
    
    -- Metadaten
    is_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID,
    
    -- Constraints
    UNIQUE(mandant_guid, theme_name),
    FOREIGN KEY (mandant_guid) REFERENCES mandant(mandant_guid) ON DELETE CASCADE
);

-- Indizes für Performance
CREATE INDEX IF NOT EXISTS idx_layout_mandant ON sys_layout(mandant_guid);
CREATE INDEX IF NOT EXISTS idx_layout_theme ON sys_layout(theme_name);
CREATE INDEX IF NOT EXISTS idx_layout_default ON sys_layout(mandant_guid, is_default) WHERE is_default = true;

-- Kommentare
COMMENT ON TABLE sys_layout IS 'Mandantenspezifische Themes (Hell/Dunkel) mit Farben, Fonts, Assets';
COMMENT ON COLUMN sys_layout.colors IS 'JSON: primary, secondary, neutral, success, warning, error, background, text, border';
COMMENT ON COLUMN sys_layout.typography IS 'JSON: fontFamily, fontSize (mit scale), fontWeight, lineHeight';
COMMENT ON COLUMN sys_layout.customizations IS 'JSON: animations, shadows, borderRadius, spacing';
COMMENT ON COLUMN sys_layout.assets IS 'JSON: logo (light/dark), icons, backgrounds';


-- Basis-Layout-Konfiguration einfügen (Dashboard)
-- ============================================================================
INSERT INTO sys_central_layout (layout_name, layout_type, layout_config, description)
VALUES (
    'Dashboard Base Layout',
    'dashboard_base',
    '{
        "structure": {
            "header_height": "64px",
            "sidebar_width": "240px",
            "sidebar_collapsed_width": "60px",
            "horizontal_menu_height": "48px",
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
            },
            "sidebar": {
                "mobile": "drawer",
                "tablet": "collapsed",
                "laptop": "full",
                "monitor": "full"
            }
        },
        "zIndex": {
            "dropdown": 1000,
            "sticky": 1020,
            "fixed": 1030,
            "modal_backdrop": 1040,
            "modal": 1050,
            "popover": 1060,
            "tooltip": 1070
        }
    }'::jsonb,
    'Basis-Layout für Dashboard mit Sidebar, Header, Content-Area'
)
ON CONFLICT (layout_name) DO NOTHING;


-- Login Layout
INSERT INTO sys_central_layout (layout_name, layout_type, layout_config, description)
VALUES (
    'Login Page Layout',
    'login',
    '{
        "structure": {
            "container_max_width": "450px",
            "card_padding": "48px"
        },
        "position": "center",
        "background": "gradient"
    }'::jsonb,
    'Zentriertes Login-Formular'
)
ON CONFLICT (layout_name) DO NOTHING;


-- Mandanten-Auswahl Layout
INSERT INTO sys_central_layout (layout_name, layout_type, layout_config, description)
VALUES (
    'Mandant Selection Layout',
    'mandant_select',
    '{
        "structure": {
            "container_max_width": "900px",
            "card_width": "280px",
            "card_gap": "24px"
        },
        "display": "grid",
        "columns_desktop": 3,
        "columns_tablet": 2,
        "columns_mobile": 1
    }'::jsonb,
    'Grid-Layout für Mandanten-Auswahl'
)
ON CONFLICT (layout_name) DO NOTHING;


-- Trigger für updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_layout_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_central_layout_updated
    BEFORE UPDATE ON sys_central_layout
    FOR EACH ROW
    EXECUTE FUNCTION update_layout_timestamp();

CREATE TRIGGER trigger_layout_updated
    BEFORE UPDATE ON sys_layout
    FOR EACH ROW
    EXECUTE FUNCTION update_layout_timestamp();


-- ============================================================================
-- Fertig! Tabellen für Layout-System erstellt
-- ============================================================================
