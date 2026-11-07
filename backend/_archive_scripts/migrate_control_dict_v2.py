"""
Phase 1: Control Dictionary V2 - Schema erweitern
==================================================

Erweitert sys_control_dict um:
- modul_type (view/edit/tabs)
- parent_guid (Hierarchie)
- SELF_NAME (automatisch generiert)
"""

import asyncio
import asyncpg
import json
import uuid

DEFAULT_DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

def generate_self_name(table: str, field: str) -> str:
    """
    Generiert SELF_NAME nach Schema: [3-Buchstaben]_[feldname]
    
    Beispiele:
    - table='persondaten', field='familienname' → 'per_familienname'
    - table='sys_framedaten', field='ROOT_TABLE' → 'sys_root_table'
    """
    prefix = table[:3].lower() if table and len(table) >= 3 else "xxx"
    field_clean = field.lower().replace(' ', '_')
    return f"{prefix}_{field_clean}"


async def migrate_control_dict_v2():
    """Migriert bestehende sys_control_dict Einträge zu V2 Schema"""
    conn = await asyncpg.connect(DEFAULT_DB_URL)
    
    try:
        print("="*80)
        print("🔧 PHASE 1: Control Dictionary V2 Migration")
        print("="*80)
        
        # 1. Alle Controls laden
        rows = await conn.fetch('SELECT uid, daten FROM sys_control_dict WHERE historisch = 0')
        
        print(f"\n📊 Gefunden: {len(rows)} Controls")
        
        migrated_count = 0
        skipped_count = 0
        
        for row in rows:
            uid = row['uid']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            # Prüfe ob bereits migriert
            if 'modul_type' in daten and 'SELF_NAME' in daten:
                skipped_count += 1
                continue
            
            # 2. modul_type bestimmen
            ctrl_type = daten.get('type', '').lower()
            gruppe = daten.get('gruppe', '').upper()
            
            # Heuristik für modul_type:
            if ctrl_type == 'element_list':
                if gruppe == 'TABS' or 'tab' in daten.get('name', '').lower():
                    modul_type = 'tabs'
                elif gruppe == 'FIELDS':
                    modul_type = 'edit'
                else:
                    modul_type = 'view'  # Default for element_list
            else:
                # Normale Controls sind edit (vorerst)
                modul_type = 'edit'
            
            # 3. SELF_NAME generieren
            table = daten.get('table', '')
            field = daten.get('feld', daten.get('name', 'unknown'))
            
            if table and field:
                self_name = generate_self_name(table, field)
            else:
                # Fallback wenn Daten fehlen
                name = daten.get('name', str(uid)[:8])
                self_name = f"ctrl_{name}"
            
            # 4. parent_guid (erstmal null - später manuell setzen)
            parent_guid = None
            
            # 5. Daten aktualisieren
            daten['modul_type'] = modul_type
            daten['SELF_NAME'] = self_name
            daten['parent_guid'] = parent_guid
            
            # 6. In DB schreiben
            await conn.execute(
                'UPDATE sys_control_dict SET daten = $1, modified_at = NOW() WHERE uid = $2',
                json.dumps(daten),
                uid
            )
            
            migrated_count += 1
            
            # Ausgabe (erste 10)
            if migrated_count <= 10:
                label = daten.get('label', daten.get('name', 'N/A'))
                print(f"  ✅ {label}")
                print(f"     modul_type={modul_type}, SELF_NAME={self_name}")
        
        print(f"\n📊 Migration abgeschlossen:")
        print(f"  ✅ Migriert: {migrated_count}")
        print(f"  ⏭️  Übersprungen: {skipped_count}")
        
        # 7. Verifikation
        print(f"\n🔍 Verifikation:")
        sample = await conn.fetch("""
            SELECT uid, daten->>'label' as label, 
                   daten->>'modul_type' as modul_type,
                   daten->>'SELF_NAME' as self_name
            FROM sys_control_dict 
            WHERE historisch = 0
            LIMIT 5
        """)
        
        for row in sample:
            print(f"  • {row['label']}: {row['modul_type']} ({row['self_name']})")
        
        print("\n" + "="*80)
        print("✅ PHASE 1 ABGESCHLOSSEN")
        print("="*80)
        print("\nNächste Schritte:")
        print("  1. Prüfe modul_type Zuordnungen (ggf. manuell korrigieren)")
        print("  2. parent_guid für element_list-Children setzen")
        print("  3. Phase 2: Frame-Struktur standardisieren")
        
    finally:
        await conn.close()


async def validate_self_name_uniqueness():
    """Prüft SELF_NAME auf Kollisionen"""
    conn = await asyncpg.connect(DEFAULT_DB_URL)
    
    try:
        print("\n🔍 Prüfe SELF_NAME Eindeutigkeit...")
        
        # Suche Duplikate
        duplicates = await conn.fetch("""
            SELECT daten->>'SELF_NAME' as self_name, COUNT(*) as count
            FROM sys_control_dict
            WHERE historisch = 0
            GROUP BY daten->>'SELF_NAME'
            HAVING COUNT(*) > 1
        """)
        
        if duplicates:
            print(f"\n⚠️  Gefunden: {len(duplicates)} doppelte SELF_NAMEs")
            for row in duplicates:
                print(f"  • {row['self_name']}: {row['count']}x")
            print("\n  → Benötigt manuelle Korrektur (z.B. Suffix _01, _02)")
        else:
            print("  ✅ Alle SELF_NAMEs sind eindeutig")
        
    finally:
        await conn.close()


async def show_migration_summary():
    """Zeigt Statistik nach Migration"""
    conn = await asyncpg.connect(DEFAULT_DB_URL)
    
    try:
        print("\n📊 Control Dictionary V2 - Statistik:")
        print("-"*80)
        
        # Nach modul_type gruppieren
        stats = await conn.fetch("""
            SELECT daten->>'modul_type' as modul_type, COUNT(*) as count
            FROM sys_control_dict
            WHERE historisch = 0
            GROUP BY daten->>'modul_type'
            ORDER BY count DESC
        """)
        
        print("\nControls nach modul_type:")
        for row in stats:
            mt = row['modul_type'] or 'null'
            count = row['count']
            print(f"  • {mt}: {count}")
        
        # Element lists
        element_lists = await conn.fetchval("""
            SELECT COUNT(*)
            FROM sys_control_dict
            WHERE historisch = 0
            AND daten->>'type' = 'element_list'
        """)
        print(f"\nElement Lists: {element_lists}")
        
        # Mit parent_guid
        with_parent = await conn.fetchval("""
            SELECT COUNT(*)
            FROM sys_control_dict
            WHERE historisch = 0
            AND daten->>'parent_guid' IS NOT NULL
            AND daten->>'parent_guid' != 'null'
        """)
        print(f"Controls mit parent_guid: {with_parent}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate_control_dict_v2())
    asyncio.run(validate_self_name_uniqueness())
    asyncio.run(show_migration_summary())
