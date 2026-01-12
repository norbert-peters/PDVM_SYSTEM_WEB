"""
Test Theme-Persistierung
Prüft ob Theme-Präferenz korrekt in sys_systemsteuerung gespeichert wird
"""
import asyncio
import uuid
from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung


async def test_theme_persistence():
    """Testet set_user_value und get_user_value für THEME_MODE"""
    
    # Test-UUIDs
    user_guid = uuid.UUID("f05b62ef-0f41-4fd7-ba98-408ce6adba6c")
    mandant_guid = uuid.UUID("f05b62ef-0f41-4fd7-ba98-408ce6adba6c")
    
    print(f"📋 Test Theme-Persistierung")
    print(f"   User: {user_guid}")
    print(f"   Mandant: {mandant_guid}")
    print()
    
    # GCS initialisieren
    gcs = PdvmCentralSystemsteuerung(user_guid, mandant_guid)
    
    # 1. Aktuellen Wert lesen
    print("1️⃣ Lese aktuellen Theme-Modus...")
    current_theme = gcs.get_user_value("THEME_MODE")
    print(f"   Aktuell: {current_theme}")
    print()
    
    # 2. Neuen Wert setzen
    new_theme = "dark" if current_theme != "dark" else "light"
    print(f"2️⃣ Setze neuen Theme-Modus: {new_theme}")
    gcs.set_user_value("THEME_MODE", new_theme)
    print("   ✅ set_user_value erfolgreich")
    print()
    
    # 3. Persistent speichern
    print("3️⃣ Speichere persistent in DB...")
    result = await gcs.save_all_values()
    print(f"   ✅ save_all_values erfolgreich: {result}")
    print()
    
    # 4. Neu laden und prüfen
    print("4️⃣ Erstelle neue GCS-Instanz und lade Daten...")
    gcs2 = PdvmCentralSystemsteuerung(user_guid, mandant_guid)
    loaded_theme = gcs2.get_user_value("THEME_MODE")
    print(f"   Geladener Theme-Modus: {loaded_theme}")
    print()
    
    # 5. Validierung
    if loaded_theme == new_theme:
        print("✅ SUCCESS: Theme-Persistierung funktioniert korrekt!")
    else:
        print(f"❌ FEHLER: Gesetzt={new_theme}, Geladen={loaded_theme}")
    print()
    
    # 6. Zeige Datenstruktur
    print("6️⃣ Datenstruktur in sys_systemsteuerung:")
    all_data = gcs2.get_all_values()
    user_data = all_data.get(str(user_guid), {})
    print(f"   {str(user_guid)}: {user_data}")


if __name__ == "__main__":
    asyncio.run(test_theme_persistence())
