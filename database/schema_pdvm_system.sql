-- PDVM System Database Schema
-- PostgreSQL 14+
-- Database: pdvm_system
-- Purpose: System configuration tables (UI, menus, dialogs, layouts)

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
            gilt_bis TEXT DEFAULT ''9999365.00000'',
            created_at TIMESTAMP DEFAULT NOW(),
            modified_at TIMESTAMP DEFAULT NOW(),
            daten_backup JSONB
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
-- SYSTEM CONFIGURATION TABLES
-- ========================================
SELECT create_pdvm_table('sys_beschreibungen');
SELECT create_pdvm_table('sys_ext_table');
SELECT create_pdvm_table('sys_dialogdaten');
SELECT create_pdvm_table('sys_framedaten');
SELECT create_pdvm_table('sys_viewdaten');
SELECT create_pdvm_table('sys_menudaten');
SELECT create_pdvm_table('sys_layout');
SELECT create_pdvm_table('sys_dropdowndaten');
SELECT create_pdvm_table('sys_systemdaten');

COMMENT ON DATABASE pdvm_system IS 'PDVM System Database - UI configuration and system metadata';
