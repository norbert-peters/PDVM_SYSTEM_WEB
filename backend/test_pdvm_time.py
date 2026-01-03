"""
Test PDVM Zeit-Utilities
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.pdvm_time import (
    datetime_to_pdvm,
    pdvm_to_datetime,
    now_pdvm,
    pdvm_format_display,
    pdvm_add_days
)
from datetime import datetime

print("🕐 PDVM Zeit-Utilities Test")
print("=" * 60)
print()

# Aktuell
now = now_pdvm()
print(f"Jetzt (PDVM):    {now}")
print(f"Jetzt (Display): {pdvm_format_display(now)}")
print()

# Konvertierung
dt = datetime(2025, 12, 22, 15, 20, 32)
pdvm = datetime_to_pdvm(dt)
print(f"DateTime:        {dt}")
print(f"PDVM:            {pdvm}")
print(f"Display:         {pdvm_format_display(pdvm)}")
print()

# Rückkonvertierung
back = pdvm_to_datetime(pdvm)
print(f"Zurück:          {back}")
print()

# Tage addieren
in_7_days = pdvm_add_days(now, 7)
print(f"In 7 Tagen:      {pdvm_format_display(in_7_days)}")
print()

# Beispiele aus Benutzer
print("📊 Beispiel-Zeitstempel:")
examples = [
    ("LAST_PASSWORD_CHANGE", 2025356.152032),
    ("AUDIT.MODIFIED_AT", 2025303.154748),
    ("Jahreswechsel", 2025001.0),
    ("Jahresende", 2025365.235959)
]

for name, pdvm_time in examples:
    print(f"  {name:25} {pdvm_time:15.6f} → {pdvm_format_display(pdvm_time)}")

print()
print("✅ Alle Tests erfolgreich!")
