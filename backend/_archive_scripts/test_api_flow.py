#!/usr/bin/env python3
"""Teste Login und Mandanten-Auswahl API"""
import asyncio
import httpx

API_BASE = "http://localhost:8000/api"

async def test_flow():
    print("🧪 Teste Login-Flow...\n")
    
    async with httpx.AsyncClient() as client:
        # 1. Login
        print("1️⃣ Login mit admin@example.com...")
        login_response = await client.post(
            f"{API_BASE}/auth/login",
            data={
                "username": "admin@example.com",
                "password": "admin"
            }
        )
        
        if login_response.status_code != 200:
            print(f"❌ Login fehlgeschlagen: {login_response.status_code}")
            print(login_response.text)
            return
        
        login_data = login_response.json()
        token = login_data['access_token']
        print(f"✅ Login erfolgreich! Token: {token[:20]}...")
        
        # 2. Mandanten-Liste
        print("\n2️⃣ Lade Mandanten-Liste...")
        mandanten_response = await client.get(
            f"{API_BASE}/mandanten/list",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if mandanten_response.status_code != 200:
            print(f"❌ Mandanten-Liste fehlgeschlagen: {mandanten_response.status_code}")
            print(mandanten_response.text)
            return
        
        mandanten = mandanten_response.json()
        print(f"✅ {len(mandanten)} Mandanten gefunden:")
        for m in mandanten:
            print(f"   - {m['name']} (allowed: {m['is_allowed']})")
        
        # 3. Mandant auswählen
        if mandanten:
            first_mandant = mandanten[0]
            print(f"\n3️⃣ Wähle Mandant: {first_mandant['name']}...")
            
            select_response = await client.post(
                f"{API_BASE}/mandanten/select",
                json={"mandant_id": first_mandant['id']},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if select_response.status_code != 200:
                print(f"❌ Mandanten-Auswahl fehlgeschlagen: {select_response.status_code}")
                print(select_response.text)
                return
            
            select_data = select_response.json()
            print(f"✅ Mandant ausgewählt: {select_data['mandant_name']}")
            
            # 4. Startmenü laden
            print("\n4️⃣ Lade Startmenü...")
            menu_response = await client.get(
                f"{API_BASE}/menu/user/start",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if menu_response.status_code != 200:
                print(f"❌ Startmenü fehlgeschlagen: {menu_response.status_code}")
                print(menu_response.text)
                return
            
            menu_data = menu_response.json()
            print(f"✅ Startmenü geladen: {menu_data.get('name')}")
            
            vertikal = menu_data.get('menu_data', {}).get('VERTIKAL', {})
            print(f"   VERTIKAL: {len(vertikal)} Items")
            
            print("\n✅ Kompletter Flow erfolgreich!")

if __name__ == "__main__":
    asyncio.run(test_flow())
