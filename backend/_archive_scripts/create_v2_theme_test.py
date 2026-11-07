"""
Erstellt ein V2-kompatibles Theme-Paket in sys_layout
und verknüpft es mit dem Admin-Mandanten und Admin-User.
"""
import asyncio
import uuid
import json
import logging
from app.core.database import db_manager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- V2 THEME DEFINITION ---
THEME_UUID = "aaaa0000-0000-0000-0000-000000000001"
THEME_NAME = "V2_Standard_Theme"

# Styles definieren (CSS Properties)
BLOCKS_LIGHT = {
    "block_header_std": {
        "bg_color": "#ffffff",
        "text_color": "#111827",
        "border_bottom": "1px solid #e5e7eb",
        "shadow": "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
    },
    "block_input_std": {
        "bg_color": "#ffffff",
        "border": "1px solid #d1d5db",
        "text_color": "#111827",
        "radius": "0.375rem"
    },
    "block_btn_primary": {
        "bg_color": "#3b82f6",
        "text_color": "#ffffff",
        "radius": "0.5rem",
        "hover_bg": "#2563eb"
    },
    "block_surface_main": {
        "bg_color": "#f3f4f6"
    }
}

BLOCKS_DARK = {
    "block_header_std": {
        "bg_color": "#1f2937",
        "text_color": "#f9fafb",
        "border_bottom": "1px solid #374151",
        "shadow": "0 1px 3px 0 rgba(0, 0, 0, 0.3)"
    },
    "block_input_std": {
        "bg_color": "#374151",
        "border": "1px solid #4b5563",
        "text_color": "#f9fafb",
        "radius": "0.375rem"
    },
    "block_btn_primary": {
        "bg_color": "#3b82f6",
        "text_color": "#ffffff",
        "radius": "0.5rem",
        "hover_bg": "#2563eb"
    },
    "block_surface_main": {
        "bg_color": "#111827"
    }
}

# Gesamtes Daten-Objekt (Die "Gruppen")
THEME_DATA = {
    "Standard_Light": BLOCKS_LIGHT,
    "Standard_Dark": BLOCKS_DARK,
    "info": {
        "name": "Standard V2 Theme",
        "version": "1.0"
    }
}

async def setup_v2_theme():
    await db_manager.connect()
    
    try:
        pool = db_manager.get_system_pool()
        
        # 1. Theme in sys_layout einfügen
        logger.info(f"💾 Speichere Theme {THEME_UUID}...")
        async with pool.acquire() as conn:
            # Lösche existierendes Test-Theme
            await conn.execute("DELETE FROM pdvm_system.sys_layout WHERE uuid = $1", 
                             uuid.UUID(THEME_UUID))
            
            # Neu einfügen
            await conn.execute("""
                INSERT INTO pdvm_system.sys_layout (uuid, daten, historisch, created_at)
                VALUES ($1, $2, 0, NOW())
            """, uuid.UUID(THEME_UUID), json.dumps(THEME_DATA))
            
        # 2. Mandant finden (Admin Mandant)
        # Wir nehmen an, wir arbeiten mit dem Admin-User/Mandant aus vorherigen Tests
        logger.info("🔍 Suche Admin-Mandant...")
        mandant_uuid = None
        user_uuid = None
        
        async with pool.acquire() as conn:
            # Mandant 'Admin Mandant' suchen
            row = await conn.fetchrow("""
                SELECT uuid, daten FROM pdvm_system.sys_mandanten 
                WHERE daten->>'name' LIKE 'Admin%' LIMIT 1
            """)
            if row:
                mandant_uuid = row['uuid']
                m_data = json.loads(row['daten'])
                
                # Update Mandant CONFIG
                if 'CONFIG' not in m_data: m_data['CONFIG'] = {}
                m_data['CONFIG']['THEME_GUID'] = THEME_UUID
                
                # Speichern
                await conn.execute("""
                    UPDATE pdvm_system.sys_mandanten 
                    SET daten = $1 
                    WHERE uuid = $2
                """, json.dumps(m_data), mandant_uuid)
                logger.info(f"✅ Mandant {mandant_uuid} aktualisiert mit THEME_GUID")
            
            # User 'admin' suchen
            row_user = await conn.fetchrow("""
                SELECT uuid, daten FROM pdvm_system.sys_benutzer 
                WHERE daten->>'username' = 'admin' LIMIT 1
            """)
            if row_user:
                user_uuid = row_user['uuid']
                u_data = json.loads(row_user['daten'])
                
                # Update User CONFIG
                if 'CONFIG' not in u_data: u_data['CONFIG'] = {}
                u_data['CONFIG']['THEME_LIGHT'] = "Standard_Light"
                u_data['CONFIG']['THEME_DARK'] = "Standard_Dark"
                
                # Speichern
                await conn.execute("""
                    UPDATE pdvm_system.sys_benutzer 
                    SET daten = $1 
                    WHERE uuid = $2
                """, json.dumps(u_data), user_uuid)
                logger.info(f"✅ User {user_uuid} aktualisiert mit THEME_LIGHT/DARK")

    except Exception as e:
        logger.error(f"❌ Fehler: {e}")
    finally:
        await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(setup_v2_theme())
