"""
Test: Error-Handling für MODUL-Auswahl

Demonstriert:
1. POST /record OHNE modul_type → 428 Response mit available_moduls
2. Frontend kann dann Modul-Dialog zeigen
3. POST /record MIT modul_type → Success
"""

import requests
import json

BASE_URL = "http://localhost:8000"
DIALOG_GUID = "ed1cd1c7-0000-0000-0000-000000000001"


def test_modul_error_handling():
    print("🧪 Test: MODUL Error-Handling\n")
    print("=" * 60)
    
    # ===== Test 1: Create OHNE modul_type =====
    print("\n1️⃣ POST /record OHNE modul_type (sollte 428 geben)...")
    
    response = requests.post(
        f"{BASE_URL}/api/dialogs/{DIALOG_GUID}/record",
        json={"name": "test_field_ohne_modul"}
    )
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 428:
        print("   ✅ Korrekt! 428 Precondition Required")
        
        data = response.json()
        print(f"\n   Response:")
        print(f"     error: {data.get('detail', {}).get('error')}")
        print(f"     message: {data.get('detail', {}).get('message')}")
        print(f"     available_moduls: {data.get('detail', {}).get('available_moduls')}")
        print(f"     modul_group_key: {data.get('detail', {}).get('modul_group_key')}")
        print(f"     help: {data.get('detail', {}).get('help')}")
        
        # Frontend kann jetzt Modul-Dialog zeigen
        available_moduls = data.get('detail', {}).get('available_moduls', [])
        print(f"\n   ✅ Frontend zeigt Modul-Dialog mit: {available_moduls}")
    else:
        print(f"   ❌ Unexpected Status: {response.status_code}")
        print(f"   Response: {response.text}")
    
    # ===== Test 2: Create MIT modul_type =====
    print("\n\n2️⃣ POST /record MIT modul_type='edit' (sollte erfolreich sein)...")
    
    response = requests.post(
        f"{BASE_URL}/api/dialogs/{DIALOG_GUID}/record",
        json={
            "name": "test_field_mit_modul",
            "modul_type": "edit"
        }
    )
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✅ Erfolgreich!")
        
        data = response.json()
        print(f"\n   Created Control:")
        print(f"     uid: {data.get('uid')}")
        print(f"     name: {data.get('name')}")
        
        daten = data.get('daten', {})
        modul_type = daten.get('ROOT', {}).get('MODUL_TYPE')
        modul_data = daten.get('CONTROL', {}).get('MODUL', {})
        
        print(f"     MODUL_TYPE: {modul_type}")
        print(f"     MODUL Felder: {len(modul_data)} ({list(modul_data.keys())[:5]}...)")
    else:
        print(f"   ❌ Fehler: {response.status_code}")
        print(f"   Response: {response.text}")
    
    # ===== Test 3: Falscher modul_type =====
    print("\n\n3️⃣ POST /record MIT falschem modul_type (sollte 400 geben)...")
    
    response = requests.post(
        f"{BASE_URL}/api/dialogs/{DIALOG_GUID}/record",
        json={
            "name": "test_field_falsch",
            "modul_type": "invalid"
        }
    )
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 400:
        print("   ✅ Korrekt! 400 Bad Request")
        print(f"   Message: {response.json().get('detail')}")
    else:
        print(f"   ❌ Unexpected Status: {response.status_code}")
    
    print("\n" + "=" * 60)
    print("✅ Test abgeschlossen!")
    print("\nFrontend-Integration:")
    print("1. POST /record ohne modul_type")
    print("2. Bei Status 428 → detail.available_moduls lesen")
    print("3. Modul-Dialog zeigen")
    print("4. POST /record erneut mit modul_type")


if __name__ == "__main__":
    try:
        test_modul_error_handling()
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
