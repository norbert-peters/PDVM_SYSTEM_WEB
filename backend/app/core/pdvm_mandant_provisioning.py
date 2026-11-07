"""Mandanten-Tabellen-Provisionierung (reine Verschiebung aus PdvmDatabase.ensure_mandant_tables)."""

from __future__ import annotations

import asyncio
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES


async def ensure_mandant_tables(mandant_id: str, mandant_db_url: str, mandant_record: dict):
    """
    PrÃ¼ft und erstellt fehlende Tabellen fÃ¼r einen Mandanten beim Login
    
    Verwendet direkte Connection statt DatabasePool.
    LÃ¤dt CONFIG.FEATURES aus mandant_record
    und erstellt alle fehlenden Tabellen in der Mandanten-Datenbank.
    
    Args:
        mandant_id: UUID des Mandanten
        mandant_db_url: Connection-URL zur Mandanten-Datenbank
        mandant_record: Mandanten-Datensatz aus asy_mandanten (mit daten JSONB)
    """
    import logging
    import asyncpg
    logger = logging.getLogger(__name__)
    
    # 1. Tabellen-Liste aus Mandanten-Config laden
    daten = mandant_record.get("daten", {})
    config = daten.get("CONFIG", {})
    features = config.get("FEATURES", [])
    
    if not isinstance(features, list):
        features = []

    legacy_to_canonical = {
        "sys_anwendungsdaten": "msy_anwendungsdaten",
        "sys_systemsteuerung": "msy_systemsteuerung",
        "sys_layout": "msy_layout",
        "sys_security": "msy_security",
        "sys_error_log": "msy_error_log",
        "sys_error_acknowledgements": "msy_error_acknowledgments",
        "sys_error_acknowledgments": "msy_error_acknowledgments",
        "sys_ext_table_man": "msy_ext_table",
        "sys_feld_aenderungshistorie": "msy_feld_aenderungshistorie",
    }
    features = [legacy_to_canonical.get(str(t), str(t)) for t in features]
    # Entfernte Tabellen aus Features explizit ausfiltern.
    features = [
        t
        for t in features
        if t not in {"msy_control_dict", "msy_control_dict_audit", "sys_contr_dict_man", "sys_contr_dict_man_audit"}
    ]
    
    mandatory_tables = [
        "msy_anwendungsdaten",
        "msy_systemsteuerung",
        "msy_layout",
        "msy_security",
        "msy_error_log",
        "msy_error_acknowledgments",
        "msy_systemdaten",
        "msy_ext_table",
        "msy_feld_aenderungshistorie",
    ]

    all_tables = list(dict.fromkeys(mandatory_tables + features))
    
    if not all_tables:
        logger.info(f"Keine Tabellen fÃ¼r Mandant {mandant_id} konfiguriert")
        return
    
    # 2. Direkte Connection zur Mandanten-DB (mit Retry)
    max_retries = 3
    retry_delay = 0.5
    conn = None
    
    for attempt in range(max_retries):
        try:
            conn = await asyncpg.connect(mandant_db_url, timeout=10)
            break  # Erfolgreich verbunden
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"âš ï¸ Connection-Versuch {attempt + 1} fehlgeschlagen: {e}, retry in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"âŒ Alle {max_retries} Connection-Versuche fehlgeschlagen")
                raise
    
    if not conn:
        raise Exception("Konnte keine Connection zur Mandanten-DB herstellen")
    
    try:
        # 3. Existierende Tabellen ermitteln
        existing_tables = await conn.fetch("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        existing_table_names = {row['tablename'] for row in existing_tables}
        
        # 4. Fehlende Tabellen erstellen
        created_count = 0
        for table_name in all_tables:
            if table_name in existing_table_names:
                logger.info(f"âœ“ Tabelle '{table_name}' existiert bereits")
                continue
            
            try:
                # Standard PDVM-Tabellenschema (einheitlich fÃ¼r ALLE Tabellen)
                columns = ', '.join([f"{col} {definition}" for col, definition in PDVM_TABLE_COLUMNS.items()])
                
                create_sql = f"""
                CREATE TABLE {table_name} (
                    {columns}
                )
                """
                
                await conn.execute(create_sql)
                
                # Indizes erstellen
                for idx_col in PDVM_TABLE_INDEXES:
                    if idx_col == 'daten':
                        # GIN Index fÃ¼r JSONB
                        await conn.execute(f"""
                            CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col} 
                            ON {table_name} USING GIN({idx_col})
                        """)
                    else:
                        # Standard B-Tree Index
                        await conn.execute(f"""
                            CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col} 
                            ON {table_name}({idx_col})
                        """)
                
                created_count += 1
                logger.info(f"âœ… Tabelle '{table_name}' mit Standard-Schema erstellt")
            
            except Exception as e:
                logger.error(f"âŒ Fehler beim Erstellen von '{table_name}': {e}")
        
        if created_count > 0:
            logger.info(f"ðŸŽ‰ {created_count} Tabelle(n) fÃ¼r Mandant '{mandant_record['name']}' erstellt")
        else:
            logger.info(f"âœ“ Alle Tabellen fÃ¼r Mandant '{mandant_record['name']}' bereits vorhanden")
    
    finally:
        await conn.close()
