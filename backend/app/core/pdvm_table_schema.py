"""
PDVM Standard-Tabellen-Schema
Zentrale Definition der Standard-Struktur für ALLE PDVM-Tabellen (außer sys_benutzer)
"""

# Standard-Datum für unbegrenzte Gültigkeit
GILT_BIS_MAX = "9999-12-31 23:59:59"

# Standard PDVM-Tabellen-Struktur
# WICHTIG: Diese Struktur gilt für ALLE Tabellen außer sys_benutzer
PDVM_TABLE_COLUMNS = {
    'uid': 'UUID PRIMARY KEY DEFAULT uuid_generate_v4()',
    'daten': 'JSONB NOT NULL',
    'name': 'TEXT',
    'historisch': 'INTEGER DEFAULT 0',
    'source_hash': 'TEXT',
    'sec_id': 'UUID',
    'gilt_bis': f"TIMESTAMP DEFAULT '{GILT_BIS_MAX}'",
    'created_at': 'TIMESTAMP DEFAULT NOW()',
    'modified_at': 'TIMESTAMP DEFAULT NOW()',
    'daten_backup': 'JSONB DEFAULT \'{}\'::jsonb'
}

# Standard-Indizes für PDVM-Tabellen
PDVM_TABLE_INDEXES = [
    'sec_id',
    'historisch',
    'name',
    'modified_at',
    'daten'  # GIN Index
]

# System-Tabellen (pdvm_system Datenbank)
# Mandantenübergreifende Strukturdaten und Layouts
PDVM_SYSTEM_TABLES = [
    'sys_beschreibungen',
    'sys_dropdowndaten',
    'sys_menudaten',
    'sys_dialogdaten',
    'sys_viewdaten',
    'sys_framedaten',
    'sys_layout'
]

