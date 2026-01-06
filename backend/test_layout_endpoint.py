"""
Teste Layout API Endpoint direkt via HTTP
"""
import requests

# Test 1: Check if endpoint is reachable
print("=== TEST 1: Health Check ===")
try:
    r = requests.get("http://localhost:8000/health")
    print(f"✅ Backend läuft: {r.status_code}")
except Exception as e:
    print(f"❌ Backend nicht erreichbar: {e}")
    exit(1)

# Test 2: Check registered routes
print("\n=== TEST 2: API Routes ===")
try:
    r = requests.get("http://localhost:8000/openapi.json")
    if r.status_code == 200:
        data = r.json()
        layout_routes = [path for path in data.get('paths', {}).keys() if 'layout' in path]
        print(f"Layout Routes: {layout_routes}")
except Exception as e:
    print(f"❌ Fehler: {e}")

# Test 3: Test Layout API ohne Auth
print("\n=== TEST 3: Layout API (ohne Auth) ===")
mandant_uid = "e51a8688-2cca-4a16-855d-52a69677fb50"
url = f"http://localhost:8000/api/layout/{mandant_uid}/light"
try:
    r = requests.get(url)
    print(f"Status: {r.status_code}")
    if r.status_code == 401:
        print("✅ Endpoint existiert (401 = Auth required)")
    elif r.status_code == 404:
        print("❌ Endpoint nicht gefunden (404)")
    else:
        print(f"Response: {r.json()}")
except Exception as e:
    print(f"❌ Fehler: {e}")

# Test 4: Mit Token (falls vorhanden)
print("\n=== TEST 4: Layout API (mit Token) ===")
try:
    # Login first
    login_r = requests.post(
        "http://localhost:8000/api/auth/login",
        data={"username": "admin", "password": "admin"}
    )
    
    if login_r.status_code == 200:
        token = login_r.json()['access_token']
        print(f"✅ Login erfolgreich")
        
        # Try layout API with token
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=headers)
        print(f"Status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            primary = data.get('daten', {}).get('colors', {}).get('primary', {}).get('500')
            print(f"✅ Theme geladen: {primary}")
        else:
            print(f"❌ Fehler: {r.text}")
    else:
        print(f"❌ Login fehlgeschlagen: {login_r.status_code}")
        
except Exception as e:
    print(f"❌ Fehler: {e}")
