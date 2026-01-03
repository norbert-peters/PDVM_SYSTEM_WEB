import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Test Backend Root
        print("1. Teste Backend Root...")
        try:
            root = await client.get("http://localhost:8000/")
            print(f"   ✅ Status: {root.status_code}")
            print(f"   Response: {root.json()}")
        except Exception as e:
            print(f"   ❌ Fehler: {e}")
            return
        
        # 2. Test Login
        print("\n2. Teste Login...")
        try:
            login = await client.post(
                "http://localhost:8000/api/auth/login",
                data={"username": "admin@example.com", "password": "admin"}
            )
            print(f"   ✅ Status: {login.status_code}")
            
            if login.status_code == 200:
                token = login.json()['access_token']
                print(f"   Token: {token[:30]}...")
                
                # 3. Test Mandanten-Liste
                print("\n3. Teste Mandanten-Liste...")
                try:
                    mandanten = await client.get(
                        "http://localhost:8000/api/mandanten/list",
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    print(f"   ✅ Status: {mandanten.status_code}")
                    
                    if mandanten.status_code == 200:
                        data = mandanten.json()
                        print(f"   {len(data)} Mandanten gefunden")
                        for m in data:
                            print(f"      - {m['name']}")
                    else:
                        print(f"   ❌ Response: {mandanten.text}")
                        print(f"   Headers: {mandanten.headers}")
                except Exception as e:
                    print(f"   ❌ Request-Fehler: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"   ❌ Login fehlgeschlagen: {login.text}")
                
        except Exception as e:
            print(f"   ❌ Fehler: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test())
