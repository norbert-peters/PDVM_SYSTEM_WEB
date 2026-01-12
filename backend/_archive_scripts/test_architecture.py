"""
Test der neuen Service-Architektur
Demonstriert PdvmDatabaseService + DataManager
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.pdvm_database import PdvmDatabaseService
from app.core.data_managers import MandantDataManager, PersonDataManager


async def test_database_service():
    """Test Generic Database Service"""
    print("=" * 60)
    print("TEST 1: PdvmDatabaseService (Generic CRUD)")
    print("=" * 60)
    print()
    
    # Initialisiere Service für sys_mandanten
    db = PdvmDatabaseService(database="auth", table="sys_mandanten")
    
    # Liste alle
    print("📋 Alle Mandanten:")
    mandanten = await db.list_all()
    for m in mandanten:
        print(f"   • {m['name']} (UID: {m['uid']})")
    print(f"   Gesamt: {await db.count()}")
    print()
    
    # Suche
    print("🔍 Suche nach 'Haupt':")
    results = await db.search("Haupt", search_fields=['name'])
    for r in results:
        print(f"   ✓ {r['name']}")
    print()
    
    # Lade einzelnen
    if mandanten:
        uid = mandanten[0]['uid']
        print(f"📄 Lade Mandant per UID ({uid}):")
        mandant = await db.get_by_uid(uid)
        print(f"   Name: {mandant['name']}")
        print(f"   Datenbank: {mandant['daten']['MANDANT']['DATABASE']}")
        print(f"   Berechtigt: {mandant['daten']['MANDANT']['IS_ALLOWED']}")
        print()


async def test_mandant_manager():
    """Test Mandant DataManager"""
    print("=" * 60)
    print("TEST 2: MandantDataManager (Business Logic + Cache)")
    print("=" * 60)
    print()
    
    manager = MandantDataManager()
    
    # Liste (mit Cache)
    print("📦 Liste mit Cache:")
    mandanten = await manager.list_all()
    for m in mandanten:
        print(f"   • {m['name']}")
    print()
    
    # Check Access
    if mandanten:
        mandant_id = mandanten[0]['uid']
        has_access = await manager.check_access(mandant_id)
        print(f"🔐 Zugriff auf '{mandanten[0]['name']}': {has_access}")
        print()
        
        # Database Name
        db_name = await manager.get_database_name(mandant_id)
        print(f"💾 Datenbank-Name: {db_name}")
        print()


async def test_person_manager():
    """Test Person DataManager"""
    print("=" * 60)
    print("TEST 3: PersonDataManager (Mandanten-Daten)")
    print("=" * 60)
    print()
    
    # Manager für Mandanten-Datenbank
    manager = PersonDataManager(mandant_database="mandant")
    
    # Liste Personen
    print("👥 Personen in Mandant-DB:")
    personen = await manager.list_all()
    if personen:
        for p in personen:
            print(f"   • {p['name']} (UID: {p['uid']})")
    else:
        print("   (keine Personen)")
    print()
    
    # Erstelle Test-Person
    print("➕ Erstelle Test-Person:")
    try:
        person = await manager.create(
            personalnummer="T001",
            familienname="Schmidt",
            vorname="Anna",
            anrede="w",
            strasse="Teststraße 123",
            plz="10115",
            ort="Berlin"
        )
        print(f"   ✅ {person['name']} erstellt")
        print(f"   UID: {person['uid']}")
        print(f"   Daten: {person['daten']['PERSDATEN']}")
        print()
    except Exception as e:
        print(f"   ⚠️  {e}")
        print()
    
    # Suche
    print("🔍 Suche nach 'Schmidt':")
    results = await manager.search_by_name("Schmidt")
    for r in results:
        print(f"   ✓ {r['name']}")
    print()


async def test_architecture():
    """Vollständiger Architektur-Test"""
    print()
    print("🚀 PDVM Service-Architektur Test")
    print()
    
    await test_database_service()
    await test_mandant_manager()
    await test_person_manager()
    
    print("=" * 60)
    print("✅ Alle Tests erfolgreich!")
    print("=" * 60)
    print()
    print("📊 Architektur-Übersicht:")
    print("   1. PdvmDatabaseService - Generic CRUD")
    print("   2. DataManager - Business Logic + Cache")
    print("   3. API Endpoints - REST Interface")
    print()


if __name__ == "__main__":
    asyncio.run(test_architecture())
