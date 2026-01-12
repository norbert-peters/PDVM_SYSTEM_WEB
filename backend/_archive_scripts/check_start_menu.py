"""
Check if START menu exists in sys_menudaten
"""
import asyncio
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.core.pdvm_database import PdvmDatabase, DatabasePool

async def check_start_menu():
    print("=== Checking START Menu in sys_menudaten ===\n")
    
    try:
        # Create static pool (auth.db)
        await DatabasePool.create_static_pool()
        
        # Create system pool (would need actual URL, but let's try with None first)
        db = PdvmDatabase('sys_menudaten', system_pool=None, mandant_pool=None)
        
        # Check if table exists
        print("1. Checking sys_menudaten table...")
        result = await db.select_all()
        print(f"   Total records: {len(result)}")
        
        # Look for START menu
        print("\n2. Looking for MEINEAPPS.START record...")
        for record in result:
            if 'MEINEAPPS' in str(record.get('uid', '')) and 'START' in str(record.get('uid', '')):
                print(f"   Found: {record.get('uid')}")
                print(f"   Name: {record.get('name')}")
                print(f"   Has MENU field: {'MENU' in (record.get('data', {}) or {})}")
        
        # Try direct select
        print("\n3. Direct select MEINEAPPS.START...")
        try:
            start_record = await db.select_one('MEINEAPPS.START')
            if start_record:
                print(f"   Found record: {start_record.get('uid')}")
                data = start_record.get('data', {}) or {}
                if 'MENU' in data:
                    menu_data = data['MENU']
                    print(f"   MENU structure: {list(menu_data.keys()) if isinstance(menu_data, dict) else 'not a dict'}")
                else:
                    print("   WARNING: No MENU field in data!")
            else:
                print("   NOT FOUND!")
        except Exception as e:
            print(f"   Error: {e}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if DatabasePool._pool_auth:
            await DatabasePool._pool_auth.close()

if __name__ == "__main__":
    asyncio.run(check_start_menu())
