#!/usr/bin/env python3
"""Prüfe ob Admin User MEINEAPPS.START.MENU hat"""
import asyncio
import asyncpg
import json

async def check_user():
    conn = await asyncpg.connect("postgresql://postgres:Polari$55@localhost:5432/auth")
    
    try:
        res = await conn.fetchrow(
            "SELECT daten FROM benutzer WHERE uid = $1",
            "aa24be4a-d95c-401f-8e6d-f0a2a6140a56"
        )
        
        if not res:
            print("❌ User nicht gefunden!")
            return
        
        data = json.loads(res['daten']) if isinstance(res['daten'], str) else res['daten']
        
        print(f"📋 User gefunden!")
        print(f"\n🔍 MEINEAPPS Struktur:")
        meineapps = data.get('MEINEAPPS', {})
        print(json.dumps(meineapps, indent=2))
        
        start_menu = meineapps.get('START', {}).get('MENU')
        print(f"\n🎯 START.MENU GUID: {start_menu}")
        
        if not start_menu:
            print("⚠️ Kein START.MENU definiert!")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_user())
