"""
Testet Layout API direkt
"""
import asyncio
from app.core.pdvm_database import PdvmDatabaseService

async def test_layout_api():
    db = PdvmDatabaseService(database="pdvm_system", table="sys_layout")
    
    print("=== TEST: List all layouts ===\n")
    all_layouts = await db.list_all(historisch=0)
    print(f"Gefunden: {len(all_layouts)} Layouts")
    
    # Zeige erste 3
    for layout in all_layouts[:3]:
        mandant_name = layout.get('daten', {}).get('mandant_name')
        theme = layout.get('daten', {}).get('theme')
        primary = layout.get('daten', {}).get('colors', {}).get('primary', {}).get('500')
        print(f"  - {mandant_name} ({theme}): {primary}")
    
    print("\n=== TEST: Get specific theme ===\n")
    # Filiale Test 1 - Orange
    mandant_uid = "e51a8688-2cca-4a16-855d-52a69677fb50"
    
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
            primary = colors.get('primary', {}).get('500')
            print(f"Filiale Test 1 (Light): {primary}")
            print(f"Full primary scale: {colors.get('primary', {})}")

if __name__ == "__main__":
    asyncio.run(test_layout_api())
