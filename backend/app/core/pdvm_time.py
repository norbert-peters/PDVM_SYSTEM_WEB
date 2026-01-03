"""
PDVM Zeit-Utilities
Konvertierung zwischen Python datetime und PDVM-Format YYYYDDD.Zeitanteil
"""
from datetime import datetime, timedelta
from typing import Union


def datetime_to_pdvm(dt: datetime) -> float:
    """
    Konvertiert datetime zu PDVM-Format: YYYYDDD.Zeitanteil
    
    Args:
        dt: Python datetime Objekt
        
    Returns:
        Float im Format YYYYDDD.HHMMSS (z.B. 2025356.143025)
    
    Beispiel:
        >>> datetime_to_pdvm(datetime(2025, 12, 22, 14, 30, 25))
        2025356.143025
    """
    # Tag des Jahres (1-366)
    day_of_year = dt.timetuple().tm_yday
    
    # Zeitanteil als Dezimalzahl: HHMMSS
    time_part = dt.hour * 10000 + dt.minute * 100 + dt.second
    time_decimal = time_part / 1000000.0  # Als Dezimalbruch
    
    # YYYYDDD + .Zeitanteil
    pdvm_time = dt.year * 1000 + day_of_year + time_decimal
    
    return pdvm_time


def pdvm_to_datetime(pdvm_time: float) -> datetime:
    """
    Konvertiert PDVM-Format zurück zu datetime
    
    Args:
        pdvm_time: Float im Format YYYYDDD.Zeitanteil
        
    Returns:
        Python datetime Objekt
        
    Beispiel:
        >>> pdvm_to_datetime(2025356.143025)
        datetime(2025, 12, 22, 14, 30, 25)
    """
    # Jahr und Tag des Jahres extrahieren
    year_and_day = int(pdvm_time)
    year = year_and_day // 1000
    day_of_year = year_and_day % 1000
    
    # Zeitanteil extrahieren
    time_fraction = pdvm_time - year_and_day
    time_int = int(time_fraction * 1000000)
    
    hours = time_int // 10000
    minutes = (time_int % 10000) // 100
    seconds = time_int % 100
    
    # Datum aus Jahr + Tag des Jahres berechnen
    date = datetime(year, 1, 1) + timedelta(days=day_of_year - 1)
    
    # Zeit hinzufügen
    result = datetime(
        date.year, date.month, date.day,
        hours, minutes, seconds
    )
    
    return result


def now_pdvm() -> float:
    """
    Gibt aktuelle Zeit im PDVM-Format zurück
    
    Returns:
        Float im Format YYYYDDD.Zeitanteil
        
    Beispiel:
        >>> now_pdvm()
        2025356.143025
    """
    return datetime_to_pdvm(datetime.now())


def pdvm_to_string(pdvm_time: float) -> str:
    """
    Formatiert PDVM-Zeit als lesbaren String
    
    Args:
        pdvm_time: PDVM-Zeitstempel
        
    Returns:
        String im Format "YYYY-MM-DD HH:MM:SS"
    """
    dt = pdvm_to_datetime(pdvm_time)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def string_to_pdvm(date_string: str) -> float:
    """
    Parst Datum-String zu PDVM-Format
    
    Args:
        date_string: String im Format "YYYY-MM-DD" oder "YYYY-MM-DD HH:MM:SS"
        
    Returns:
        PDVM-Zeitstempel
    """
    try:
        # Mit Zeit
        dt = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            # Nur Datum
            dt = datetime.strptime(date_string, "%Y-%m-%d")
        except ValueError:
            # ISO Format
            dt = datetime.fromisoformat(date_string)
    
    return datetime_to_pdvm(dt)


# Convenience Funktionen
def pdvm_date_only(pdvm_time: float) -> float:
    """
    Gibt nur Datums-Teil zurück (ohne Zeitanteil)
    
    Args:
        pdvm_time: PDVM-Zeitstempel
        
    Returns:
        PDVM-Zeitstempel mit .0 als Zeitanteil
    """
    return float(int(pdvm_time))


def pdvm_add_days(pdvm_time: float, days: int) -> float:
    """
    Addiert Tage zu PDVM-Zeitstempel
    
    Args:
        pdvm_time: PDVM-Zeitstempel
        days: Anzahl Tage
        
    Returns:
        Neuer PDVM-Zeitstempel
    """
    dt = pdvm_to_datetime(pdvm_time)
    new_dt = dt + timedelta(days=days)
    return datetime_to_pdvm(new_dt)


def pdvm_format_display(pdvm_time: float) -> str:
    """
    Formatiert PDVM-Zeit für Anzeige (DE-Format)
    
    Args:
        pdvm_time: PDVM-Zeitstempel
        
    Returns:
        String im Format "DD.MM.YYYY HH:MM"
    """
    if pdvm_time == 0.0:
        return ""
    
    dt = pdvm_to_datetime(pdvm_time)
    return dt.strftime("%d.%m.%Y %H:%M")
