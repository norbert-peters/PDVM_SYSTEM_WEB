"""Korrigiere fehlende/falsche Connection-Configs in sys_mandanten"""
import asyncio
import asyncpg
import json

async def fix_mandant_configs():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='Polari$55',
        database='auth',
        ssl=False
    )
    
    try:
        # Alle Mandanten laden (außer Templates und Properties_control)
        rows = await conn.fetch("""
            SELECT uid, name, daten 
            FROM sys_mandanten 
            WHERE historisch = 0 
            AND uid NOT IN (
                '55555555-5555-5555-5555-555555555555',  -- Properies_control
                '66666666-6666-6666-6666-666666666666'   -- Template neuer Satz
            )
            ORDER BY name
        """)
        
        print("\n=== KORRIGIERE MANDANTEN-CONFIGS ===\n")
        
        updated_count = 0
        
        for row in rows:
            uid = row['uid']
            name = row['name']
            daten_str = row['daten']
            
            # Parse JSON
            try:
                daten = json.loads(daten_str) if isinstance(daten_str, str) else daten_str
            except:
                print(f"⚠️ {name}: Kann daten nicht parsen - überspringe")
                continue
            
            if not daten:
                print(f"⚠️ {name}: Keine daten vorhanden - überspringe")
                continue
            
            mandant_config = daten.get('MANDANT', {})
            if not mandant_config:
                print(f"⚠️ {name}: Keine MANDANT-Config - überspringe")
                continue
            
            # Prüfe ob Updates nötig sind
            needs_update = False
            updates = []
            
            # 1. Prüfe PASSWORD
            current_pwd = mandant_config.get('PASSWORD', '')
            if current_pwd != 'Polari$55':
                needs_update = True
                updates.append(f"PASSWORD: '{current_pwd}' → 'Polari$55'")
                mandant_config['PASSWORD'] = 'Polari$55'
            
            # 2. Prüfe SYSTEM_DB
            if 'SYSTEM_DB' not in mandant_config:
                needs_update = True
                updates.append("SYSTEM_DB: FEHLT → 'pdvm_system'")
                mandant_config['SYSTEM_DB'] = 'pdvm_system'
            
            # 3. Stelle sicher dass alle Basis-Felder vorhanden sind
            if 'HOST' not in mandant_config:
                mandant_config['HOST'] = 'localhost'
                needs_update = True
                updates.append("HOST: FEHLT → 'localhost'")
            
            if 'PORT' not in mandant_config:
                mandant_config['PORT'] = 5432
                needs_update = True
                updates.append("PORT: FEHLT → 5432")
            
            if 'USER' not in mandant_config:
                mandant_config['USER'] = 'postgres'
                needs_update = True
                updates.append("USER: FEHLT → 'postgres'")
            
            # Update durchführen wenn nötig
            if needs_update:
                print(f"🔧 {name}:")
                for update in updates:
                    print(f"   - {update}")
                
                # Daten zurückschreiben
                daten['MANDANT'] = mandant_config
                new_daten_json = json.dumps(daten)
                
                await conn.execute(
                    "UPDATE sys_mandanten SET daten = $1 WHERE uid = $2",
                    new_daten_json,
                    uid
                )
                
                print(f"   ✅ UPDATE erfolgreich")
                updated_count += 1
            else:
                print(f"✓ {name}: Bereits korrekt")
            
            print()
        
        print(f"\n{'=' * 60}")
        print(f"✅ {updated_count} Mandanten aktualisiert")
        print(f"{'=' * 60}\n")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_mandant_configs())
