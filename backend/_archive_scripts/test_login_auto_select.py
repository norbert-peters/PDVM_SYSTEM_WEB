"""
Test Login Auto-Select Response
Überprüft was die Login-API für admin@example.com zurückgibt
"""

import asyncio
import httpx

async def test_login():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/auth/login",
            data={
                "username": "admin@example.com",
                "password": "admin"
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"\nResponse JSON:")
        data = response.json()
        
        print(f"  access_token: {data.get('access_token', 'MISSING')[:50]}...")
        print(f"  user_id: {data.get('user_id')}")
        print(f"  name: {data.get('name')}")
        print(f"  auto_select_mandant: {data.get('auto_select_mandant')}")
        print(f"  mandanten count: {len(data.get('mandanten', []))}")
        
        print(f"\n🔍 WICHTIG - auto_select_mandant:")
        auto_select = data.get('auto_select_mandant')
        print(f"  Typ: {type(auto_select)}")
        print(f"  Wert: {auto_select}")
        print(f"  Is None: {auto_select is None}")
        
        if data.get('mandanten'):
            print(f"\n📋 Mandanten:")
            for m in data['mandanten']:
                print(f"  - {m['id']}: {m['name']}")

if __name__ == "__main__":
    asyncio.run(test_login())
