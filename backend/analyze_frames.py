"""
Analysiert alle Frames in sys_framedaten für Phase 2 Migration
"""
import asyncio
import asyncpg
import json
from uuid import UUID

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def analyze_frames():
    """Analysiert alle Frames in sys_framedaten"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔍 Frame-Struktur Analyse (Phase 2 Vorbereitung)")
        print("=" * 80)
        
        # Alle Frames laden
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_framedaten
            WHERE historisch = 0
            ORDER BY name
        """)
        
        print(f"\n📦 {len(rows)} Frames gefunden\n")
        
        frames_ok = []
        frames_incomplete = []
        frames_missing_root = []
        
        for row in rows:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            # Falls daten als String kommt, parsen
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            print(f"\n📝 Frame: {name}")
            print(f"   UID: {uid}")
            
            # ROOT Prüfung
            if "ROOT" not in daten:
                print(f"   ❌ Kein ROOT vorhanden!")
                frames_missing_root.append((uid, name))
                continue
            
            root = daten.get("ROOT", {})
            
            # Pflichtfelder prüfen
            required_fields = {
                "ROOT_TABLE": root.get("ROOT_TABLE"),
                "SELF_GUID": root.get("SELF_GUID"),
                "SELF_NAME": root.get("SELF_NAME"),
                "TABS": root.get("TABS")
            }
            
            # Status anzeigen
            missing = []
            for field, value in required_fields.items():
                # ROOT_TABLE darf NULL sein (generische Frames)
                if field == "ROOT_TABLE":
                    if value is None:
                        print(f"   ℹ️  {field}: NULL (generic frame)")
                    elif value == "":
                        print(f"   ❌ {field}: FEHLT")
                        missing.append(field)
                    else:
                        print(f"   ✅ {field}: {value}")
                else:
                    # Andere Felder müssen vorhanden sein
                    if value is None or value == "":
                        print(f"   ❌ {field}: FEHLT")
                        missing.append(field)
                    else:
                        print(f"   ✅ {field}: {value}")
            
            # Optional: EDIT_TYPE
            edit_type = root.get("EDIT_TYPE")
            if edit_type:
                print(f"   ℹ️  EDIT_TYPE: {edit_type}")
            
            # Weitere Gruppen
            other_groups = [k for k in daten.keys() if k != "ROOT"]
            if other_groups:
                print(f"   📂 Weitere Gruppen: {', '.join(other_groups)}")
            
            # Klassifizierung
            if missing:
                frames_incomplete.append((uid, name, missing))
            else:
                frames_ok.append((uid, name))
        
        # Zusammenfassung
        print("\n" + "=" * 80)
        print("📊 ZUSAMMENFASSUNG")
        print("=" * 80)
        
        print(f"\n✅ Vollständig: {len(frames_ok)}")
        for uid, name in frames_ok:
            print(f"   - {name} ({uid})")
        
        print(f"\n⚠️  Unvollständig: {len(frames_incomplete)}")
        for uid, name, missing in frames_incomplete:
            print(f"   - {name} ({uid})")
            print(f"     Fehlt: {', '.join(missing)}")
        
        print(f"\n❌ Ohne ROOT: {len(frames_missing_root)}")
        for uid, name in frames_missing_root:
            print(f"   - {name} ({uid})")
        
        # Empfehlung
        print("\n" + "=" * 80)
        print("🎯 EMPFEHLUNG FÜR PHASE 2")
        print("=" * 80)
        
        total_to_migrate = len(frames_incomplete) + len(frames_missing_root)
        
        if total_to_migrate == 0:
            print("\n✅ Alle Frames haben vollständige ROOT-Struktur!")
            print("   Phase 2 kann übersprungen werden.")
        else:
            print(f"\n📝 {total_to_migrate} Frames müssen migriert werden:")
            print("\n   1. SELF_GUID automatisch aus Frame-UID setzen")
            print("   2. SELF_NAME aus 'name' übernehmen (falls leer)")
            print("   3. ROOT_TABLE aus Context ermitteln oder manuell setzen")
            print("   4. TABS zählen (aus TABS-Gruppe)")
            print("   5. ROOT-Gruppe erstellen (falls fehlend)")
        
        return {
            "ok": frames_ok,
            "incomplete": frames_incomplete,
            "missing_root": frames_missing_root
        }
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze_frames())
