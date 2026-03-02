"""
Einfachere Lösung: Entferne das problematische FIELDS Control vorerst
Die anderen 4 Controls sollten funktionieren.
"""
import asyncio
import asyncpg
import json

async def simplify_frame():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        frame_uuid = '4413571e-6bf6-4f42-b81a-bc898db4880c'
        
        print("="*80)
        print("🔧 Vereinfache Frame für MVP")
        print("="*80)
        
        # Frame laden
        row = await conn.fetchrow(
            'SELECT daten FROM sys_framedaten WHERE uid = $1',
            frame_uuid
        )
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        # Problematischen FIELDS Control vorerst entfernen
        fields_guid = '9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78'
        
        if fields_guid in daten.get('FIELDS', {}):
            del daten['FIELDS'][fields_guid]
            print(f"⚠️  FIELDS element_list Control entfernt (vorerst)")
            print(f"   Kann später mit speziellem Editor implementiert werden")
        
        # Zeige verbleibende Controls
        print(f"\n📦 Verbleibende Controls:")
        for control_guid, control_data in daten.get('FIELDS', {}).items():
            if isinstance(control_data, dict):
                label = control_data.get('label', '???')
                gruppe = control_data.get('gruppe', '???')
                feld = control_data.get('feld', '???')
                print(f"   ✅ {label}: {gruppe}.{feld}")
        
        # Update in DB
        await conn.execute(
            'UPDATE sys_framedaten SET daten = $1, modified_at = NOW() WHERE uid = $2',
            json.dumps(daten),
            frame_uuid
        )
        
        print("\n" + "="*80)
        print("✅ FRAME VEREINFACHT")
        print("="*80)
        
        print("\n🎯 Test-Anleitung:")
        print("   1. Backend neu starten (falls läuft)")
        print("   2. Im Browser aufrufen:")
        print(f"      http://localhost:8010/api/dialogs/.../record/{frame_uuid}")
        print("   3. Erwartung: 4 Controls mit Daten anzeigen:")
        print("      • Dialog-Name: 'Edit Frame'")
        print("      • Edit-Type: 'edit_frame'")
        print("      • Tabs: 2")
        print("      • Tabs (Liste): Dict mit 2 Einträgen")
        
        print("\n📝 Wenn auch diese nicht funktionieren:")
        print("   → Problem liegt im Frontend (nicht Backend)")
        print("   → Prüfe Browser DevTools Console für Fehler")
        print("   → Prüfe ob /api/dialogs/.../record/... korrekte Daten liefert")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(simplify_frame())
