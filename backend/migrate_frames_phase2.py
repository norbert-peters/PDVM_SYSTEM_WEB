"""
Phase 2 Migration: Frame-Struktur standardisieren
Füllt fehlende ROOT-Felder automatisch auf
"""
import asyncio
import asyncpg
import json
from uuid import UUID

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

# Mapping EDIT_TYPE → ROOT_TABLE (bekannte Zuordnungen)
EDIT_TYPE_TO_TABLE = {
    "edit_user": "sys_login",
    "edit_frame": "sys_framedaten",
    "menu": "sys_menudaten",
    "edit_json": None,  # Generic JSON editor, no specific table
    "show_json": None,  # JSON viewer, no specific table
    "import_data": None,  # Import tool, no specific table
}

async def migrate_frames():
    """Migriert alle Frames auf V2 Struktur"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔧 Phase 2: Frame-Struktur Migration")
        print("=" * 80)
        
        # Alle Frames laden
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_framedaten
            WHERE historisch = 0
            ORDER BY name
        """)
        
        print(f"\n📦 {len(rows)} Frames gefunden\n")
        
        migrated = 0
        skipped = 0
        
        for row in rows:
            uid = row['uid']
            name = row['name'] or "Unbenannt"
            daten = row['daten']
            
            # Falls daten als String kommt, parsen
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            print(f"\n📝 {name} ({uid})")
            
            # Prüfen ob ROOT existiert
            if "ROOT" not in daten:
                print(f"   ℹ️  Erstelle ROOT-Gruppe...")
                daten["ROOT"] = {}
            
            root = daten["ROOT"]
            changes = []
            
            # 1. SELF_GUID setzen (immer Frame-UID)
            if not root.get("SELF_GUID") or root.get("SELF_GUID") == "":
                root["SELF_GUID"] = str(uid)
                changes.append("SELF_GUID")
            
            # 2. SELF_NAME setzen (aus name-Feld)
            if not root.get("SELF_NAME") or root.get("SELF_NAME") == "":
                root["SELF_NAME"] = name
                changes.append("SELF_NAME")
            
            # 3. TABS zählen (aus TABS-Gruppe)
            if not root.get("TABS") or root.get("TABS") == "":
                tabs_count = 0
                if "TABS" in daten:
                    tabs_count = len(daten["TABS"])
                root["TABS"] = tabs_count
                changes.append(f"TABS={tabs_count}")
            
            # 4. ROOT_TABLE ermitteln (semi-automatisch)
            if not root.get("ROOT_TABLE") or root.get("ROOT_TABLE") == "":
                edit_type = root.get("EDIT_TYPE")
                
                if edit_type and edit_type in EDIT_TYPE_TO_TABLE:
                    table = EDIT_TYPE_TO_TABLE[edit_type]
                    if table:
                        root["ROOT_TABLE"] = table
                        changes.append(f"ROOT_TABLE={table}")
                    else:
                        root["ROOT_TABLE"] = None
                        changes.append("ROOT_TABLE=NULL (generic)")
                else:
                    # Kein bekannter EDIT_TYPE, NULL setzen
                    root["ROOT_TABLE"] = None
                    changes.append("ROOT_TABLE=NULL (unknown)")
            
            # Update durchführen
            if changes:
                await conn.execute("""
                    UPDATE public.sys_framedaten
                    SET daten = $1,
                        modified_at = NOW()
                    WHERE uid = $2
                """, json.dumps(daten), uid)
                
                print(f"   ✅ Migriert: {', '.join(changes)}")
                migrated += 1
            else:
                print(f"   ⏭️  Bereits vollständig")
                skipped += 1
        
        # Zusammenfassung
        print("\n" + "=" * 80)
        print("📊 MIGRATIONS-ERGEBNIS")
        print("=" * 80)
        print(f"\n   ✅ Migriert: {migrated}")
        print(f"   ⏭️  Übersprungen: {skipped}")
        print(f"   📦 Gesamt: {len(rows)}")
        
        # Validierung
        print("\n" + "=" * 80)
        print("🔍 Validierung")
        print("=" * 80)
        
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_framedaten
            WHERE historisch = 0
        """)
        
        complete = 0
        incomplete = 0
        
        for row in rows:
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            if "ROOT" not in daten:
                incomplete += 1
                continue
            
            root = daten["ROOT"]
            required = ["SELF_GUID", "SELF_NAME", "TABS", "ROOT_TABLE"]
            
            if all(field in root for field in required):
                # ROOT_TABLE kann NULL sein (generic frames)
                complete += 1
            else:
                incomplete += 1
        
        print(f"\n   ✅ Vollständig: {complete}")
        print(f"   ⚠️  Unvollständig: {incomplete}")
        
        if incomplete == 0:
            print("\n🎉 Phase 2 ABGESCHLOSSEN!")
        else:
            print("\n⚠️  Einige Frames benötigen manuelle Nacharbeit")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_frames())
