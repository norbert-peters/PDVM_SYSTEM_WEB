"""
Teste Layout API für verschiedene Mandanten
"""
import asyncio
from app.core.pdvm_database import PdvmDatabaseService

async def test_all_mandanten():
    db = PdvmDatabaseService(database="pdvm_system", table="sys_layout")
    
    mandanten = [
        ("e51a8688-2cca-4a16-855d-52a69677fb50", "Filiale Test 1 - ORANGE"),
        ("790a8e80-92f6-43b9-92fa-90d5699c6709", "Filiale Test 2 - BLAU"),
        ("91b106b8-b90b-4450-a07b-4eb3556dc407", "Ganz neu - GRÜN"),
        ("1804094a-a8fc-4c58-b9ad-d837a15b98e6", "PDVM Hauptmandant - ORANGE"),
        ("55555555-5555-5555-5555-555555555555", "Properies_control - GRÜN"),
        ("66666666-6666-6666-6666-666666666666", "Template neuer Satz - BLAU"),
    ]
    
    all_layouts = await db.list_all(historisch=0)
    
    print("=== THEME TEST FÜR ALLE MANDANTEN ===\n")
    
    for mandant_uid, mandant_name in mandanten:
        # Filtere nach mandant_uid
        mandant_layouts = [
            l for l in all_layouts
            if l.get('daten', {}).get('mandant_uid') == mandant_uid
        ]
        
        if mandant_layouts:
            light_theme = next(
                (l for l in mandant_layouts if l.get('daten', {}).get('theme') == 'light'),
                None
            )
            
            if light_theme:
                colors = light_theme.get('daten', {}).get('colors', {})
                primary = colors.get('primary', {}).get('500', 'N/A')
                stored_name = light_theme.get('daten', {}).get('mandant_name', 'N/A')
                stored_uid = light_theme.get('daten', {}).get('mandant_uid', 'N/A')
                
                print(f"✅ {mandant_name}")
                print(f"   Stored Name: {stored_name}")
                print(f"   Stored UID:  {stored_uid}")
                print(f"   Query UID:   {mandant_uid}")
                print(f"   Primary:     {primary}")
                print()
        else:
            print(f"❌ {mandant_name}")
            print(f"   Keine Layouts gefunden für UID: {mandant_uid}")
            print()

if __name__ == "__main__":
    asyncio.run(test_all_mandanten())
