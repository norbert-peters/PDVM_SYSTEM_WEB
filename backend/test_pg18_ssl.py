"""
Test PostgreSQL 18 mit verschiedenen SSL-Modi
"""
import asyncio
import asyncpg
import ssl

async def test():
    configs = [
        ("Standard", {}),
        ("SSL disabled", {"ssl": False}),
        ("SSL prefer", {"ssl": "prefer"}),
        ("SSL allow", {"ssl": "allow"}),
        ("SSL disable explicit", {"ssl": "disable"}),
    ]
    
    for name, ssl_config in configs:
        print(f"\n{name}:")
        try:
            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                user="postgres",
                password="Norbertw1958",
                database="postgres",
                timeout=5,
                **ssl_config
            )
            version = await conn.fetchval("SELECT version()")
            await conn.close()
            print(f"✅ SUCCESS: {version[:80]}")
            return  # Erfolg gefunden, stoppe
        except Exception as e:
            print(f"❌ {type(e).__name__}: {str(e)[:100]}")

asyncio.run(test())
