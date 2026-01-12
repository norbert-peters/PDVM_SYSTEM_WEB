"""Test Theme API with full login flow"""
import requests

BASE_URL = "http://localhost:8000"

# 1. Login
print("1️⃣ Login...")
login_response = requests.post(
    f"{BASE_URL}/api/auth/login",
    data={"username": "admin@example.com", "password": "admin"}
)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)
    exit(1)

data = login_response.json()
token = data["access_token"]
mandanten = data["mandanten"]
print(f"✅ Login successful")
print(f"   Token: {token[:50]}...")
print(f"   Mandanten: {len(mandanten)}")

# 2. Select first mandant
print(f"\n   First mandant structure: {mandanten[0]}")
mandant_uid = mandanten[0]["id"]  # Key is "id"
print(f"\n2️⃣ Select Mandant: {mandanten[0]['name']} ({mandant_uid})")

headers = {"Authorization": f"Bearer {token}"}
select_response = requests.post(
    f"{BASE_URL}/api/auth/select-mandant/{mandant_uid}",
    headers=headers
)

if select_response.status_code != 200:
    print(f"❌ Mandant selection failed: {select_response.status_code}")
    print(select_response.text)
    exit(1)

print(f"✅ Mandant selected")

# 3. Test theme preference (this should now work)
print(f"\n3️⃣ Get Theme Preference...")
theme_response = requests.get(
    f"{BASE_URL}/api/layout/preferences/theme",
    headers=headers
)

print(f"Status: {theme_response.status_code}")
print(f"Response: {theme_response.text}")

if theme_response.status_code == 500:
    print("\n❌ 500 Error - checking logs...")
elif theme_response.status_code == 200:
    print("\n✅ Theme API working")
