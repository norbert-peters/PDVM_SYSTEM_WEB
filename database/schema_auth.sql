-- Authentication Database Schema
-- PostgreSQL 14+
-- Database: auth
-- Purpose: User authentication and tenant management

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
-- AUTHENTICATION TABLES
-- ========================================

-- sys_benutzer (Users with special columns)
CREATE TABLE IF NOT EXISTS sys_benutzer (
    uid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    benutzer TEXT UNIQUE NOT NULL,  -- Email/Username
    passwort TEXT NOT NULL,         -- Password hash
    daten JSONB NOT NULL,
    name TEXT,
    historisch INTEGER DEFAULT 0,
    source_hash TEXT,
    sec_id UUID,
    gilt_bis TEXT DEFAULT '9999365.00000',
    created_at TIMESTAMP DEFAULT NOW(),
    modified_at TIMESTAMP DEFAULT NOW(),
    daten_backup JSONB
);

CREATE INDEX idx_sys_benutzer_benutzer ON sys_benutzer(benutzer);
CREATE INDEX idx_sys_benutzer_sec_id ON sys_benutzer(sec_id);
CREATE INDEX idx_sys_benutzer_daten ON sys_benutzer USING GIN(daten);

-- sys_mandanten (Clients/Tenants)
SELECT create_pdvm_table('sys_mandanten');

-- ========================================
-- DEMO DATA
-- ========================================

-- Create admin user (password: admin - CHANGE IN PRODUCTION!)
INSERT INTO sys_benutzer (uid, benutzer, passwort, daten, name)
VALUES (
    'a0000000-0000-0000-0000-000000000001'::uuid,
    'admin@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYNJL8Zk7Sy', -- "admin"
    '{"SETTINGS": {"LAND": "DEU"}}',
    'Administrator'
) ON CONFLICT (benutzer) DO NOTHING;

COMMENT ON DATABASE auth IS 'PDVM Authentication Database - Users and tenants';
