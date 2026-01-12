"""
Test Menu API
"""
import asyncio
import httpx

BASE_URL = "http://localhost:8000"
LOGIN_DATA = {
    "username": "admin@example.com",
    "password": "admin"
}

async def test_menu_api():
    """Testet die Menu API"""
    
    async with httpx.AsyncClient() as client:
        # 1. Login
        print("1️⃣ Login...")
        response = await client.post(f"{BASE_URL}/api/auth/login", data=LOGIN_DATA)
        
        if response.status_code != 200:
            print(f"❌ Login fehlgeschlagen: {response.status_code}")
            print(response.text)
            return
        
        login_result = response.json()
        token = login_result['access_token']
        print(f"✅ Login erfolgreich")
        print(f"   Token: {token[:20]}...")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. User Start Menu laden
        print("\n2️⃣ Lade User Startmenü...")
        response = await client.get(f"{BASE_URL}/api/menu/user/start", headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Fehler: {response.status_code}")
            print(response.text)
            return
        
        menu = response.json()
        print(f"✅ Startmenü geladen")
        print(f"   Name: {menu['name']}")
        print(f"   UID: {menu['uid']}")
        
        # Menü-Struktur anzeigen
        menu_data = menu['menu_data']
        
        print(f"\n📊 Menü-Struktur:")
        print(f"   VERTIKAL ({len(menu_data['VERTIKAL'])} Items):")
        for item_guid, item in sorted(menu_data['VERTIKAL'].items(), key=lambda x: x[1].get('sort_order', 999)):
            label = item.get('label', 'Unbekannt')
            item_type = item.get('type', 'UNKNOWN')
            print(f"     [{item.get('sort_order', '?')}] {label} ({item_type})")
        
        print(f"\n   GRUND ({len(menu_data['GRUND'])} Items):")
        for item_guid, item in sorted(menu_data['GRUND'].items(), key=lambda x: x[1].get('sort_order', 999)):
            label = item.get('label', 'Unbekannt')
            item_type = item.get('type', 'UNKNOWN')
            parent = f" [→ parent]" if item.get('parent_guid') else ""
            print(f"     [{item.get('sort_order', '?')}] {label} ({item_type}){parent}")
        
        print(f"\n   ROOT:")
        for key, value in menu_data['ROOT'].items():
            print(f"     {key}: {value}")
        
        # 3. Flache Items-Liste laden
        print(f"\n3️⃣ Lade flache Items-Liste...")
        response = await client.get(
            f"{BASE_URL}/api/menu/items/{menu['uid']}/flat",
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"❌ Fehler: {response.status_code}")
            print(response.text)
            return
        
        flat_menu = response.json()
        print(f"✅ {len(flat_menu['items'])} Items geladen")
        
        print(f"\n📋 Alle Items:")
        for item in flat_menu['items'][:10]:  # Erste 10
            gruppe = item.get('gruppe', '?')
            label = item.get('label', 'Unbekannt')
            item_type = item.get('type', 'UNKNOWN')
            print(f"   [{gruppe}] {label} ({item_type})")
        
        print("\n✅ Alle Tests erfolgreich!")


if __name__ == "__main__":
    print("=" * 70)
    print("Menu API Test")
    print("=" * 70)
    asyncio.run(test_menu_api())
    print("=" * 70)
