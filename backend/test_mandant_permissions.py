"""
Test-Script für Mandanten-Berechtigungen

Zeigt verschiedene Szenarien:
1. User mit mehreren Mandanten (normale Auswahl)
2. User mit nur einem Mandant (Auto-Select via DEFAULT)
3. User ohne Berechtigung (Fehler)
"""
import asyncio
import asyncpg
import json

async def test_permissions():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='Polari$55',
        database='auth',
        ssl=False
    )
    
    try:
        print("\n" + "="*60)
        print("MANDANTEN-BERECHTIGUNGEN TEST")
        print("="*60 + "\n")
        
        # Lade alle User
        users = await conn.fetch("""
            SELECT uid, name, benutzer, daten
            FROM sys_benutzer
            WHERE historisch = 0
            ORDER BY name
        """)
        
        for user in users:
            name = user['name']
            benutzer = user['benutzer']
            daten_str = user['daten']
            
            # Parse JSON
            try:
                daten = json.loads(daten_str) if isinstance(daten_str, str) else daten_str
            except:
                daten = {}
            
            mandanten_config = daten.get('MANDANTEN', {})
            mandanten_list = mandanten_config.get('LIST', [])
            default_mandant = mandanten_config.get('DEFAULT')
            
            print(f"👤 {name} ({benutzer})")
            print(f"   LIST: {len(mandanten_list)} Mandanten")
            
            if mandanten_list:
                # Zeige Namen der erlaubten Mandanten
                mandant_names = []
                for mid in mandanten_list:
                    mandant = await conn.fetchrow(
                        "SELECT name FROM sys_mandanten WHERE uid = $1",
                        mid
                    )
                    if mandant:
                        mandant_names.append(mandant['name'])
                
                print(f"        → {', '.join(mandant_names)}")
            else:
                print(f"        → (leer)")
            
            print(f"   DEFAULT: {default_mandant or '(nicht gesetzt)'}")
            
            # Verhalten vorhersagen
            if not mandanten_list and not default_mandant:
                print(f"   ❌ VERHALTEN: Fehler 'Keine Zulassung zu einem Mandanten'")
            elif not mandanten_list and default_mandant:
                print(f"   ✅ VERHALTEN: Auto-Select → Direkt zu DEFAULT-Mandant")
            elif mandanten_list:
                if len(mandanten_list) == 1:
                    print(f"   ✅ VERHALTEN: Normale Auswahl (1 Mandant)")
                else:
                    print(f"   ✅ VERHALTEN: Normale Auswahl ({len(mandanten_list)} Mandanten)")
            
            print()
        
        print("="*60)
        print("EMPFOHLENE TEST-KONFIGURATIONEN:")
        print("="*60)
        print("""
Szenario 1: Multi-Mandant User (admin)
  MANDANTEN.LIST = ["uid1", "uid2", "uid3"]
  MANDANTEN.DEFAULT = "uid1"
  → Zeigt Auswahl-Dialog mit 3 Mandanten

Szenario 2: Single-Mandant User (auto-select)
  MANDANTEN.LIST = []
  MANDANTEN.DEFAULT = "uid1"
  → Verzweigt direkt zu DEFAULT-Mandant (kein Dialog)

Szenario 3: Gesperrter User (keine Berechtigung)
  MANDANTEN.LIST = []
  MANDANTEN.DEFAULT = null
  → Fehler: "Keine Zulassung zu einem Mandanten"
        """)
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_permissions())
