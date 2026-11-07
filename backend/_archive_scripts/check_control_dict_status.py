"""
Prüft aktuellen Status der sys_control_dict Controls
"""
import asyncio
import asyncpg
import json

async def check_control_dict_status():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        print("="*80)
        print("🔍 Control Dictionary Status Check")
        print("="*80)
        
        # Alle Controls mit neuen Feldern
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM sys_control_dict
            WHERE historisch = 0
            ORDER BY daten->>'modul_type', daten->>'SELF_NAME'
            LIMIT 15
        """)
        
        print(f"\n📦 Control Dictionary Einträge ({len(rows)} gezeigt):\n")
        
        for row in rows:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            label = daten.get('label', 'N/A')
            modul_type = daten.get('modul_type', 'FEHLT')
            self_name = daten.get('SELF_NAME', 'FEHLT')
            parent_guid = daten.get('parent_guid')
            ctrl_type = daten.get('type', 'N/A')
            
            print(f"📝 {name or uid[:8]}")
            print(f"   Label: {label}")
            print(f"   Type: {ctrl_type}")
            print(f"   modul_type: {modul_type}")
            print(f"   SELF_NAME: {self_name}")
            print(f"   parent_guid: {parent_guid}")
            print()
        
        # Statistik
        print("="*80)
        print("📊 Statistik")
        print("="*80)
        
        stats = await conn.fetch("""
            SELECT 
                daten->>'modul_type' as modul_type,
                daten->>'type' as ctrl_type,
                COUNT(*) as count
            FROM sys_control_dict
            WHERE historisch = 0
            GROUP BY daten->>'modul_type', daten->>'type'
            ORDER BY daten->>'modul_type', count DESC
        """)
        
        print("\nControls nach Typ:")
        for row in stats:
            mt = row['modul_type'] or 'null'
            ct = row['ctrl_type'] or 'unknown'
            count = row['count']
            print(f"  {mt:8} / {ct:15} : {count:2}")
        
        # Label-Check
        print("\n" + "="*80)
        print("🔍 Label-Check (sollte nicht None sein)")
        print("="*80)
        
        no_label = await conn.fetch("""
            SELECT uid, name, daten->>'SELF_NAME' as self_name
            FROM sys_control_dict
            WHERE historisch = 0
            AND (daten->>'label' IS NULL OR daten->>'label' = '')
            LIMIT 10
        """)
        
        if no_label:
            print(f"\n⚠️  {len(no_label)} Controls ohne Label gefunden:")
            for row in no_label:
                print(f"  • {row['name'] or row['uid'][:8]}: {row['self_name']}")
        else:
            print("\n✅ Alle Controls haben ein Label")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_control_dict_status())
