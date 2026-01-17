"""
Application Configuration
Environment variables and settings
"""
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    """Application settings from environment variables"""

    # =========================================================================
    # AUTH DATABASE - Die einzige fix konfigurierte Datenbank
    # =========================================================================
    # Diese Datenbank enthält:
    # - sys_benutzer (User-Accounts, Credentials)
    # - sys_mandanten (Mandanten-Definitionen + Connection-Configs)
    # Alle anderen Datenbanken werden dynamisch aus sys_mandanten geladen!
    DATABASE_URL_AUTH: str = "postgresql://postgres:Polari$55@localhost:5432/auth"

    # Auth
    SECRET_KEY: str = "your-secret-key-change-this"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]

    # =========================================================================
    # VIEW PIPELINE SCALING
    # =========================================================================
    # Wie viele Zeilen pro Tabelle maximal in Session-Cache gehalten werden.
    # (Schutz vor RAM-Explosion; für sehr große Tabellen später DB-seitiges Paging/Query-Pushdown via PdvmDatabase-Adapter.)
    VIEW_TABLE_CACHE_MAX_ROWS: int = 20000

    # Chunk-Size für initiales Laden (LIMIT/OFFSET Paging). 
    VIEW_TABLE_CACHE_CHUNK_SIZE: int = 2000

    # Minimaler Abstand (Sekunden) zwischen Delta-Refresh (modified_at > max_modified_at) pro Tabelle.
    VIEW_TABLE_CACHE_REFRESH_MIN_INTERVAL_SECONDS: float = 2.0

    # Max Anzahl gecachter Matrix-Resultate (UID-Order) pro Session.
    VIEW_MATRIX_RESULT_CACHE_MAX_ENTRIES: int = 200

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
