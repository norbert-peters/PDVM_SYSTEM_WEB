"""
Setup Mandanten in Datenbank
Erstellt die Standard-Mandanten mit DataManager
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.data_managers import MandantDataManager


async def setup_mandanten():
    """Erstellt Standard-Mandanten"""
    
    manager = MandantDataManager()
    
    print("🏗️  Setup Mandanten...")
    print()
    
    # Mandant 1: Hauptmandant (berechtigt)
    try:
        mandant1 = await manager.create(
            name="PDVM Hauptmandant",
            database="mandant",
            description="Produktiver Hauptmandant",
            is_allowed=True,
            config={
                "features": ["persondaten", "finanzdaten"],
                "max_users": 100
            }
        )
        print(f"✅ Mandant 1 erstellt:")
        print(f"   Name: {mandant1['name']}")
        print(f"   UID: {mandant1['uid']}")
        print(f"   Datenbank: {mandant1['daten']['MANDANT']['DATABASE']}")
        print(f"   Berechtigt: {mandant1['daten']['MANDANT']['IS_ALLOWED']}")
        print()
    except Exception as e:
        print(f"⚠️  Mandant 1: {e}")
        print()
    
    # Mandant 2: Test-Mandant (nicht berechtigt)
    try:
        mandant2 = await manager.create(
            name="Test Mandant",
            database="test_mandant",
            description="Gesperrt - Keine Berechtigung",
            is_allowed=False,
            config={
                "features": [],
                "max_users": 0
            }
        )
        print(f"✅ Mandant 2 erstellt:")
        print(f"   Name: {mandant2['name']}")
        print(f"   UID: {mandant2['uid']}")
        print(f"   Datenbank: {mandant2['daten']['MANDANT']['DATABASE']}")
        print(f"   Berechtigt: {mandant2['daten']['MANDANT']['IS_ALLOWED']}")
        print()
    except Exception as e:
        print(f"⚠️  Mandant 2: {e}")
        print()
    
    # Liste alle Mandanten
    print("📋 Alle Mandanten:")
    mandanten = await manager.list_all()
    for m in mandanten:
        status = "✅ Berechtigt" if m['daten']['MANDANT']['IS_ALLOWED'] else "❌ Gesperrt"
        print(f"   • {m['name']} - {status}")
        print(f"     UID: {m['uid']}")
        print(f"     DB: {m['daten']['MANDANT']['DATABASE']}")
    
    print()
    print("🎉 Setup abgeschlossen!")


if __name__ == "__main__":
    asyncio.run(setup_mandanten())
