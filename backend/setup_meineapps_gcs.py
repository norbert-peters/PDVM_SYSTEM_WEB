"""
Setze MEINEAPPS für Admin-User über PdvmCentralSystemsteuerung
Ultra-einfache Desktop-Struktur!
"""
import asyncio
import asyncpg
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
from app.core.database import DatabasePool

ADMIN_USER_GUID = "2e3c7b09-65eb-46e3-b5ec-fa163fb3a9b6"
MANDANT_GUID = "11111111-1111-1111-1111-111111111111"  # Test-Mandant
STARTMENU_GUID = "5ca6674e-b9ce-4581-9756-64e742883f80"

async def setup_meineapps():
    print("🔧 Setze MEINEAPPS über GCS (Desktop-Pattern)...\n")
    
    try:
        # 1. Erstelle Pools
        await DatabasePool.create_pool()  # auth pool
        
        # System und Mandant Pools direkt erstellen
        system_pool = await asyncpg.create_pool("postgresql://postgres:Polari$55@localhost:5432/pdvm_system")
        mandant_pool = await asyncpg.create_pool("postgresql://postgres:Polari$55@localhost:5432/mandanten")
        
        # 2. Erstelle GCS-Instanz
        gcs = PdvmCentralSystemsteuerung(
            user_guid=ADMIN_USER_GUID,
            mandant_guid=MANDANT_GUID,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        
        # 3. Prüfe aktuellen MEINEAPPS-Wert
        print("1. Aktueller MEINEAPPS:")
        current = gcs.get_user_value("MEINEAPPS")
        print(f"   {current}\n")
        
        # 4. Setze MEINEAPPS-Struktur
        meineapps = {
            "START": {
                "MENU": STARTMENU_GUID
            },
            "PERSONALWESEN": {
                "MENU": "dummy-guid-personalwesen"
            },
            "FINANZWESEN": {
                "MENU": "dummy-guid-finanzwesen"
            },
            "BENUTZERDATEN": {
                "MENU": "dummy-guid-benutzerdaten"
            },
            "ADMINISTRATION": {
                "MENU": "dummy-guid-administration"
            },
            "TESTBEREICH": {
                "MENU": "dummy-guid-testbereich"
            }
        }
        
        print("2. Setze MEINEAPPS über gcs.set_user_value():")
        await gcs.set_user_value("MEINEAPPS", meineapps)
        print("   ✅ Gesetzt!\n")
        
        # 5. Verifiziere
        print("3. Verifikation:")
        updated = gcs.get_user_value("MEINEAPPS")
        print(f"   MEINEAPPS.START.MENU = {updated.get('START', {}).get('MENU') if isinstance(updated, dict) else 'ERROR'}")
        
    finally:
        # Cleanup
        if DatabasePool._pool_auth:
            await DatabasePool._pool_auth.close()
        if system_pool:
            await system_pool.close()
        if mandant_pool:
            await mandant_pool.close()

if __name__ == "__main__":
    asyncio.run(setup_meineapps())
