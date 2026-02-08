-- Mandant Database Schema
-- PostgreSQL 14+
-- Database: mandant (or specific tenant name)
-- Purpose: Tenant-specific application data and settings

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ========================================
-- STANDARD TABLE FUNCTION
-- Creates PDVM-compliant table with standard columns
-- ========================================
CREATE OR REPLACE FUNCTION create_pdvm_table(table_name TEXT) 
RETURNS void AS $$
BEGIN
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I (
            uid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            daten JSONB NOT NULL,
            name TEXT,
            historisch INTEGER DEFAULT 0,
            source_hash TEXT,
            sec_id UUID,
            gilt_bis TIMESTAMP DEFAULT ''9999-12-31 23:59:59'',
            created_at TIMESTAMP DEFAULT NOW(),
            modified_at TIMESTAMP DEFAULT NOW(),
            daten_backup JSONB DEFAULT ''{}''::jsonb
        );
        
        CREATE INDEX IF NOT EXISTS idx_%I_sec_id ON %I(sec_id);
        CREATE INDEX IF NOT EXISTS idx_%I_historisch ON %I(historisch);
        CREATE INDEX IF NOT EXISTS idx_%I_name ON %I(name);
        CREATE INDEX IF NOT EXISTS idx_%I_modified_at ON %I(modified_at);
        CREATE INDEX IF NOT EXISTS idx_%I_daten ON %I USING GIN(daten);
    ', table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name);
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- MANDANT SYSTEM TABLES
-- ========================================
SELECT create_pdvm_table('sys_anwendungsdaten');
SELECT create_pdvm_table('sys_ext_table_man');
SELECT create_pdvm_table('sys_systemsteuerung');
SELECT create_pdvm_table('sys_security');
SELECT create_pdvm_table('sys_error_log');
SELECT create_pdvm_table('sys_error_acknowledgments');

-- ========================================
-- APPLICATION BUSINESS TABLES
-- ========================================
SELECT create_pdvm_table('persondaten');
SELECT create_pdvm_table('finanzdaten');

-- ========================================
-- DEMO DATA
-- ========================================

-- Create demo person
INSERT INTO persondaten (uid, daten, name)
VALUES (
    'ed21cb69-046b-465f-b231-6e75852b50b3'::uuid,
    '{
        "ROOT": {},
        "PERSDATEN": {
            "PERSONALNUMMER": {"2025043.0": "A1"},
            "FAMILIENNAME": {"2025043.0": "Mustermann"},
            "VORNAME": {"2025043.0": "Max"},
            "ANREDE": {"2025043.0": "m"},
            "GEBURTSDATUM": {"2025043.0": 1972218.0}
        },
        "ANSCHRIFT_PERSON": {
            "STRASSE": {"2025043.0": "Hauptstraße 1"},
            "PLZ": {"2025043.0": "10115"},
            "ORT": {"2025043.0": "Berlin"}
        }
    }',
    'Max Mustermann'
) ON CONFLICT (uid) DO NOTHING;

COMMENT ON DATABASE mandant IS 'PDVM Mandant Database - Tenant application data';
