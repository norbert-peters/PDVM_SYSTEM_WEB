"""
Teste GCS-API über HTTP-Requests (Backend muss laufen!)
"""
import requests
import json

# API Base URL
API_BASE = "http://localhost:8000"

# Test-Credentials (admin@example.com / admin)
# Token muss vorher über Login geholt werden

def test_gcs_api():
    print("=" * 60)
    print("GCS API Test (über Backend)")
    print("=" * 60)
    
    # 1. Login um Token zu bekommen
    print("\n1️⃣ Login...")
    login_response = requests.post(
        f"{API_BASE}/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "admin"
        }
    )
    
    if login_response.status_code != 200:
        print(f"   ❌ Login fehlgeschlagen: {login_response.status_code}")
        print(f"   {login_response.text}")
        return
    
    token = login_response.json()["access_token"]
    print(f"   ✅ Token erhalten: {token[:20]}...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Mandant wählen
    print("\n2️⃣ Wähle Mandant...")
    mandant_response = requests.post(
        f"{API_BASE}/api/auth/select-mandant",
        headers=headers,
        json={"mandant_id": "00000000-0000-0000-0000-000000000001"}
    )
    
    if mandant_response.status_code != 200:
        print(f"   ❌ Mandant-Auswahl fehlgeschlagen: {mandant_response.status_code}")
        print(f"   {mandant_response.text}")
        return
    
    print("   ✅ Mandant gewählt")
    
    # Test-Daten
    menu_guid = "3424b00f-bb4d-4759-9689-e9e08249117b"  # Admin-Menü
    
    # 3. Setze toggle_menu auf 0 (ausgeblendet)
    print(f"\n3️⃣ Setze toggle_menu=0 für Menü {menu_guid[:8]}...")
    set_response = requests.post(
        f"{API_BASE}/api/gcs/value",
        headers=headers,
        json={
            "gruppe": menu_guid,
            "feld": "toggle_menu",
            "value": 0
        }
    )
    
    print(f"   Status: {set_response.status_code}")
    if set_response.status_code == 200:
        print(f"   ✅ Gespeichert: {set_response.json()}")
    else:
        print(f"   ❌ Fehler: {set_response.text}")
        return
    
    # 4. Lade toggle_menu Status
    print(f"\n4️⃣ Lade toggle_menu Status...")
    get_response = requests.get(
        f"{API_BASE}/api/gcs/value",
        headers=headers,
        params={
            "gruppe": menu_guid,
            "feld": "toggle_menu"
        }
    )
    
    print(f"   Status: {get_response.status_code}")
    if get_response.status_code == 200:
        data = get_response.json()
        print(f"   ✅ Geladen: {data}")
        print(f"      → Wert: {data['value']}")
    elif get_response.status_code == 404:
        print(f"   ℹ️ Wert nicht gefunden (404)")
    else:
        print(f"   ❌ Fehler: {get_response.text}")
    
    # 5. Update auf 1 (eingeblendet)
    print(f"\n5️⃣ Update auf toggle_menu=1...")
    update_response = requests.post(
        f"{API_BASE}/api/gcs/value",
        headers=headers,
        json={
            "gruppe": menu_guid,
            "feld": "toggle_menu",
            "value": 1
        }
    )
    
    print(f"   Status: {update_response.status_code}")
    if update_response.status_code == 200:
        print(f"   ✅ Aktualisiert: {update_response.json()}")
    else:
        print(f"   ❌ Fehler: {update_response.text}")
    
    # 6. Prüfe Update
    print(f"\n6️⃣ Prüfe aktualisierten Wert...")
    check_response = requests.get(
        f"{API_BASE}/api/gcs/value",
        headers=headers,
        params={
            "gruppe": menu_guid,
            "feld": "toggle_menu"
        }
    )
    
    if check_response.status_code == 200:
        data = check_response.json()
        print(f"   ✅ Neuer Wert: {data['value']}")
        
        if data['value'] == 1:
            print("\n" + "=" * 60)
            print("✅ GCS API Test erfolgreich!")
            print("=" * 60)
        else:
            print(f"\n   ⚠️ Wert stimmt nicht: erwartet 1, erhalten {data['value']}")
    else:
        print(f"   ❌ Fehler beim Laden: {check_response.text}")

if __name__ == "__main__":
    try:
        test_gcs_api()
    except requests.exceptions.ConnectionError:
        print("\n❌ Kann Backend nicht erreichen!")
        print("   → Starte Backend mit: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
