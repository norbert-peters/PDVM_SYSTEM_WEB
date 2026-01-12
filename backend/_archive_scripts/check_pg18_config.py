"""
Finde PostgreSQL 18 Konfiguration und Port
"""
import winreg
import os

try:
    # PostgreSQL 18 Registry-Key
    key_path = r"SOFTWARE\PostgreSQL\Installations\postgresql-x64-18"
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
    
    try:
        data_dir, _ = winreg.QueryValueEx(key, "Data Directory")
        print(f"Data Directory: {data_dir}")
        
        # Lese postgresql.conf
        conf_file = os.path.join(data_dir, "postgresql.conf")
        if os.path.exists(conf_file):
            print(f"\nPostgreSQL Config: {conf_file}")
            with open(conf_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if 'port' in line.lower() or 'listen' in line.lower() or 'max_connections' in line.lower():
                            print(f"  {line}")
        
        # Lese pg_hba.conf
        hba_file = os.path.join(data_dir, "pg_hba.conf")
        if os.path.exists(hba_file):
            print(f"\nPG_HBA Config: {hba_file}")
            with open(hba_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        print(f"  {line}")
                        
    finally:
        winreg.CloseKey(key)
        
except FileNotFoundError:
    print("PostgreSQL 18 Registry-Key nicht gefunden")
except Exception as e:
    print(f"Fehler: {e}")
