"""
Test Theme-Persistierung über API
Prüft POST/GET /api/layout/preferences/theme Endpoints
"""
import requests
import json

# API Base URL
BASE_URL = "http://localhost:8000"

# Test-User Login (Admin)
def login():
    """Login und Token holen"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": "admin@example.com",
            "password": "admin"
        }
    )
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"❌ Login fehlgeschlagen: {response.status_code}")
        print(response.text)
        return None


def test_theme_api():
    """Test Theme-Persistierung über API"""
    
    print("📋 Test Theme-Persistierung über API")
    print()
    
    # 1. Login
    print("1️⃣ Login...")
    token = login()
    if not token:
        return
    print(f"   ✅ Token erhalten: {token[:20]}...")
    print()
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Aktuelle Präferenz lesen
    print("2️⃣ Lese aktuelle Theme-Präferenz...")
    response = requests.get(
        f"{BASE_URL}/api/layout/preferences/theme",
        headers=headers
    )
    print(f"   Status: {response.status_code}")
    current = {}  # Default
    if response.status_code == 200:
        current = response.json()
        print(f"   Aktuell: {json.dumps(current, indent=2)}")
    else:
        print(f"   Fehler: {response.text}")
        current = {"theme_mode": "light"}  # Default für weiteren Test
    print()
    
    # 3. Neues Theme setzen
    new_theme = "dark" if current.get("theme_mode") != "dark" else "light"
    print(f"3️⃣ Setze neues Theme: {new_theme}")
    response = requests.post(
        f"{BASE_URL}/api/layout/preferences/theme",
        params={"theme_mode": new_theme},
        headers=headers
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
    else:
        print(f"   Fehler: {response.text}")
    print()
    
    # 4. Erneut lesen zur Überprüfung
    print("4️⃣ Lese Theme-Präferenz erneut...")
    response = requests.get(
        f"{BASE_URL}/api/layout/preferences/theme",
        headers=headers
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        loaded = response.json()
        print(f"   Geladen: {json.dumps(loaded, indent=2)}")
        
        # Validierung
        if loaded.get("theme_mode") == new_theme:
            print(f"   ✅ SUCCESS: Theme korrekt persistiert!")
        else:
            print(f"   ❌ FEHLER: Gesetzt={new_theme}, Geladen={loaded.get('theme_mode')}")
    else:
        print(f"   Fehler: {response.text}")


if __name__ == "__main__":
    try:
        test_theme_api()
    except requests.exceptions.ConnectionError:
        print("❌ Backend-Server nicht erreichbar. Bitte starte den Server mit:")
        print("   cd backend && uvicorn app.main:app --reload")
    except Exception as e:
        print(f"❌ Fehler: {e}")
