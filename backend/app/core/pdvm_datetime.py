"""
PDVM DateTime - Zentrale Klasse für Zeitkonvertierung und -formatierung

Das PDVM-Zeitformat (aus der Desktop-Anwendung übernommen) verwendet intern oft floats
der Form YYYYDDD.Fraction, wobei:
- YYYY = Jahr (4-stellig)
- DDD  = Tag im Jahr (1-366)
- Fraction = Tagesanteil (0.0 bis 0.99999...), wobei 0.5 = 12:00 Uhr mittags entspricht.

Diese Klasse bietet Konvertierungsmethoden zwischen:
- Nativem Python `datetime` (für DB und API)
- PDVM-Float (für Legacy-Kompatibilität und Berechnungen)
- Formatierten Strings (für UI-Darstellung)

Autor: Norbert Peters
Portiert: 2026
"""

from datetime import datetime, timedelta, date, time as py_time
from typing import Optional, Union, Tuple
import math

# Konstanten für PDVM-Spezialwerte
SENTINEL_MIN = 1001.0       # 01.01.0001 (Minimalwert / Leer)
SENTINEL_MAX = 9999365.99999 # Max mögliches Datum

class PdvmDateTime:
    """
    Statische Helper-Klasse für DateTime Operationen im PDVM Kontext.
    In der Web-Applikation verzichten wir auf den komplexen State der Desktop-Instanz
    und nutzen stattdessen reine Funktions-Bibliotheken, da der State
    im Frontend (React) oder in der DB liegt.
    """

    @staticmethod
    def now() -> datetime:
        """Liefert das aktuelle Datum/Zeit (lokal)."""
        return datetime.now()

    @staticmethod
    def now_as_float() -> float:
        """Liefert JETZT als PDVM-Float."""
        return PdvmDateTime.datetime_to_float(datetime.now())

    @staticmethod
    def float_to_datetime(pdvm_val: Optional[float]) -> Optional[datetime]:
        """
        Konvertiert PDVM-Float (YYYYDDD.Zeit) -> Python datetime.
        """
        if pdvm_val is None or pdvm_val == 0:
            return None
        
        # Sentinel Check
        if abs(pdvm_val - SENTINEL_MIN) < 0.0001:
            return datetime(1, 1, 1) # Repräsentiert "Leer"

        try:
            val_str = f"{pdvm_val:.10f}"
            date_part = val_str.split('.')[0]
            time_part = val_str.split('.')[1]
            
            # Pad or trim date part if needed (e.g. if formatting yields less digits, though with YYYYDDD it should be ok)
            if len(date_part) < 5: 
                return None 

            yyyy = int(date_part[:4])
            ddd = int(date_part[4:])
            
            # Basis: 1. Jan des Jahres
            base_date = datetime(yyyy, 1, 1)
            # Addiere Tage (DDD - 1, da 1. Jan = Tag 1 ist)
            target_date = base_date + timedelta(days=ddd - 1)

            # Zeit berechnen: Fraction * 24 * 3600
            # Fraction ist '0.' + time_part
            fraction = float(f"0.{time_part}")
            total_seconds = fraction * 86400 # 24 * 60 * 60
            
            # Runden um Fließkomma-Ungenauigkeiten zu minimieren
            total_seconds = round(total_seconds)
            
            final_dt = target_date + timedelta(seconds=total_seconds)
            return final_dt

        except Exception as e:
            # Fallback oder Logging im Fehlerfall
            # print(f"Error converting float {pdvm_val} to datetime: {e}")
            return None

    @staticmethod
    def datetime_to_float(dt: Optional[datetime]) -> float:
        """
        Konvertiert Python datetime -> PDVM-Float (YYYYDDD.Zeit).
        """
        if dt is None:
            return SENTINEL_MIN
            
        if dt.year == 1 and dt.month == 1 and dt.day == 1:
            return SENTINEL_MIN

        # YYYYDDD berechnen
        yyyy = dt.year
        # Tag des Jahres (1-366)
        ddd = dt.timetuple().tm_yday
        
        date_part = (yyyy * 1000) + ddd
        
        # Zeitanteil berechnen
        seconds_since_midnight = (dt.hour * 3600) + (dt.minute * 60) + dt.second + (dt.microsecond / 1000000.0)
        fraction = seconds_since_midnight / 86400.0
        
        return float(date_part) + fraction

    @staticmethod
    def to_iso_string(dt: Optional[datetime]) -> Optional[str]:
        """Konvertiert datetime -> ISO 8601 String für Frontend API."""
        if dt is None:
            return None
        return dt.isoformat()

    @staticmethod
    def from_iso_string(iso_str: Optional[str]) -> Optional[datetime]:
        """Konvertiert ISO 8601 String -> datetime."""
        if not iso_str:
            return None
        try:
            return datetime.fromisoformat(iso_str)
        except ValueError:
            return None

    @staticmethod
    def format_frontend_de(dt: Optional[datetime], include_seconds: bool = True) -> str:
        """
        Formatiert für deutsche Anzeige im UI (z.B. für Tooltips oder Readonly).
        Frontend nutzt meist eigene Formatierung, aber für Server-generierte Texte nützlich.
        """
        if dt is None:
            return ""
        
        fmt = "%d.%m.%Y %H:%M"
        if include_seconds:
            fmt += ":%S"
        
        return dt.strftime(fmt)

import calendar


class PdvmDateTime:
    """
    PDVM DateTime Klasse für Zeitstempel-Verwaltung.
    
    Unterstützt:
    - Konvertierung zwischen Python datetime und PDVM-Format
    - Kalenderberechnungen (Schaltjahre, Wochentage, Monatsenden)
    - Arithmetische Operationen (Add/Subtract Jahre, Monate, Tage, Zeit)
    - Verschiedene Ausgabeformate (DIN, DEU, ENG, USA)
    - Zentrale String-Formatierung mit 5 Nachkommastellen
    """
    
    # Konstanten für Microsekunden-Berechnungen
    _MICROSEC_PER_DAY = 86400000000
    _MICROSEC_PER_HOUR = 3600000000
    _MICROSEC_PER_MINUTE = 60000000
    _MICROSEC_PER_SECOND = 1000000
    
    # Datumsformate
    DATE_FORMATS = {
        'DIN': {'splitter': '-', 'year_pos': 0, 'month_pos': 2},
        'DEU': {'splitter': '.', 'year_pos': 2, 'month_pos': 1},
        'ENG': {'splitter': '/', 'year_pos': 2, 'month_pos': 1},
        'USA': {'splitter': '/', 'year_pos': 2, 'month_pos': 0},
    }
    
    def __init__(self, form_country: str = 'DEU'):
        """
        Initialisiert PDVM DateTime Objekt.
        
        Args:
            form_country: Länderformat ('DIN', 'DEU', 'ENG', 'USA')
        """
        self.form_country = form_country.upper()
        if self.form_country not in self.DATE_FORMATS:
            self.form_country = 'DEU'
        
        self._pdvm_datetime = 0.0
        self._is_negative = False
        
        # Komponenten
        self.year = 0
        self.month = 0
        self.day = 0
        self.hour = 0
        self.minute = 0
        self.second = 0
        self.microsecond = 0
        self.yday = 0  # Tag im Jahr
    
    @property
    def pdvm_datetime(self) -> float:
        """PDVM DateTime als float."""
        return -self._pdvm_datetime if self._is_negative else self._pdvm_datetime
    
    @pdvm_datetime.setter
    def pdvm_datetime(self, value: float):
        """Setzt PDVM DateTime und zerlegt in Komponenten."""
        if value < 0:
            self._is_negative = True
            value = abs(value)
        else:
            self._is_negative = False
        
        if value < 1001.0:
            value = 1001.0
        
        self._pdvm_datetime = value
        self._split_pdvm_datetime()
    
    @property
    def pdvm_datetime_str(self) -> str:
        """
        ZENTRALE String-Formatierung mit 5 Nachkommastellen.
        
        Returns:
            str: PDVM DateTime als String mit 5 Dezimalstellen
            
        Beispiel:
            >>> pdt.pdvm_datetime_str
            '2025356.15203'
        """
        pdvm_val = self.pdvm_datetime
        
        # Prüfen ob Zeit vorhanden (Nachkommastellen != 0)
        if abs(pdvm_val - int(pdvm_val)) < 0.000001:
            # Keine Zeit -> 5 Nullen für 00:00:00.000
            return f"{int(pdvm_val)}.00000"
        else:
            # Zeit vorhanden -> 5 Nachkommastellen
            return f"{pdvm_val:.5f}"
    
    @property
    def pdvm_date(self) -> int:
        """Nur Datum (ohne Zeit)."""
        return int(self._pdvm_datetime)
    
    @property
    def pdvm_time(self) -> float:
        """Nur Zeit (Dezimalanteil)."""
        return self._pdvm_datetime - int(self._pdvm_datetime)
    
    @property
    def weekday(self) -> int:
        """Wochentag (0=Montag, 6=Sonntag)."""
        dt = self.to_datetime()
        return dt.weekday()
    
    @property
    def is_leap_year(self) -> bool:
        """Prüft ob Schaltjahr."""
        return calendar.isleap(self.year)
    
    @property
    def period(self) -> int:
        """Periode im Format YYYYMM."""
        return self.year * 100 + self.month
    
    @property
    def first_day_of_month(self) -> int:
        """Erster Tag des Monats als YYYYDDD."""
        first = datetime(self.year, self.month, 1)
        return self.year * 1000 + first.timetuple().tm_yday
    
    @property
    def last_day_of_month(self) -> int:
        """Letzter Tag des Monats als YYYYDDD."""
        last_day = calendar.monthrange(self.year, self.month)[1]
        last = datetime(self.year, self.month, last_day)
        return self.year * 1000 + last.timetuple().tm_yday
    
    @property
    def date(self) -> str:
        """Formatiertes Datum nach Länderformat."""
        fmt = self.DATE_FORMATS[self.form_country]
        
        if fmt['year_pos'] == 0:  # YYYY-MM-DD
            return f"{self.year}{fmt['splitter']}{self.month:02d}{fmt['splitter']}{self.day:02d}"
        elif fmt['month_pos'] == 0:  # MM/DD/YYYY (USA)
            return f"{self.month:02d}{fmt['splitter']}{self.day:02d}{fmt['splitter']}{self.year}"
        else:  # DD.MM.YYYY (DEU/ENG)
            return f"{self.day:02d}{fmt['splitter']}{self.month:02d}{fmt['splitter']}{self.year}"
    
    @property
    def time(self) -> str:
        """Formatierte Zeit (HH:MM:SS)."""
        return f"{self.hour:02d}:{self.minute:02d}:{self.second:02d}"
    
    @property
    def time_short(self) -> str:
        """Formatierte Zeit kurz (HH:MM)."""
        return f"{self.hour:02d}:{self.minute:02d}"
    
    @property
    def timestamp(self) -> str:
        """Vollständiger Zeitstempel (Datum - Zeit)."""
        prefix = "-" if self._is_negative else ""
        return f"{prefix}{self.date} - {self.time}"
    
    def _split_pdvm_datetime(self):
        """Zerlegt PDVM DateTime in einzelne Komponenten."""
        # Datum und Zeit trennen
        pdvm_date = int(self._pdvm_datetime)
        pdvm_time = self._pdvm_datetime - pdvm_date
        
        # Jahr und Tag im Jahr
        self.year = pdvm_date // 1000
        self.yday = pdvm_date % 1000
        
        # Datum aus Tag im Jahr berechnen
        if self.yday > 0:
            date = datetime(self.year, 1, 1) + timedelta(days=self.yday - 1)
            self.month = date.month
            self.day = date.day
        else:
            self.month = 0
            self.day = 0
        
        # Zeit aus Dezimalanteil berechnen
        total_microsec = int(pdvm_time * self._MICROSEC_PER_DAY)
        
        self.hour = total_microsec // self._MICROSEC_PER_HOUR
        rest = total_microsec % self._MICROSEC_PER_HOUR
        
        self.minute = rest // self._MICROSEC_PER_MINUTE
        rest = rest % self._MICROSEC_PER_MINUTE
        
        self.second = rest // self._MICROSEC_PER_SECOND
        self.microsecond = rest % self._MICROSEC_PER_SECOND
        
        # Korrektur für Rundungsfehler
        if self.second == 60:
            self.second = 0
        if self.microsecond > 999000:
            self.microsecond = 0
    
    def from_datetime(self, dt: datetime) -> 'PdvmDateTime':
        """
        Setzt Wert aus Python datetime.
        
        Args:
            dt: Python datetime-Objekt
            
        Returns:
            self für Method Chaining
        """
        self.year = dt.year
        self.month = dt.month
        self.day = dt.day
        self.hour = dt.hour
        self.minute = dt.minute
        self.second = dt.second
        self.microsecond = dt.microsecond
        
        # Tag im Jahr
        self.yday = dt.timetuple().tm_yday
        
        # PDVM DateTime berechnen
        pdvm_date = self.year * 1000 + self.yday
        
        total_microsec = (
            self.hour * self._MICROSEC_PER_HOUR +
            self.minute * self._MICROSEC_PER_MINUTE +
            self.second * self._MICROSEC_PER_SECOND +
            self.microsecond
        )
        time_fraction = total_microsec / self._MICROSEC_PER_DAY
        
        self._pdvm_datetime = pdvm_date + time_fraction
        
        return self
    
    def to_datetime(self) -> datetime:
        """
        Konvertiert zu Python datetime.
        
        Returns:
            datetime: Python datetime-Objekt
        """
        if self.yday > 0:
            date = datetime(self.year, 1, 1) + timedelta(days=self.yday - 1)
            return datetime(
                date.year, date.month, date.day,
                self.hour, self.minute, self.second, self.microsecond
            )
        return datetime(self.year, self.month, self.day,
                       self.hour, self.minute, self.second, self.microsecond)
    
    def now(self) -> 'PdvmDateTime':
        """Setzt auf aktuelle Zeit."""
        return self.from_datetime(datetime.now())
    
    def add_years(self, years: int) -> 'PdvmDateTime':
        """Addiert Jahre."""
        dt = self.to_datetime()
        try:
            new_dt = dt.replace(year=dt.year + years)
        except ValueError:
            # 29. Feb in Nicht-Schaltjahr -> 28. Feb
            new_dt = dt.replace(year=dt.year + years, day=28)
        return self.from_datetime(new_dt)
    
    def add_months(self, months: int) -> 'PdvmDateTime':
        """Addiert Monate."""
        total_months = self.year * 12 + self.month - 1 + months
        new_year = total_months // 12
        new_month = (total_months % 12) + 1
        
        # Tag anpassen falls nicht existiert
        max_day = calendar.monthrange(new_year, new_month)[1]
        new_day = min(self.day, max_day)
        
        dt = datetime(new_year, new_month, new_day,
                     self.hour, self.minute, self.second, self.microsecond)
        return self.from_datetime(dt)
    
    def add_days(self, days: int) -> 'PdvmDateTime':
        """Addiert Tage."""
        dt = self.to_datetime() + timedelta(days=days)
        return self.from_datetime(dt)
    
    def add_hours(self, hours: int) -> 'PdvmDateTime':
        """Addiert Stunden."""
        dt = self.to_datetime() + timedelta(hours=hours)
        return self.from_datetime(dt)
    
    def add_minutes(self, minutes: int) -> 'PdvmDateTime':
        """Addiert Minuten."""
        dt = self.to_datetime() + timedelta(minutes=minutes)
        return self.from_datetime(dt)
    
    def add_seconds(self, seconds: int) -> 'PdvmDateTime':
        """Addiert Sekunden."""
        dt = self.to_datetime() + timedelta(seconds=seconds)
        return self.from_datetime(dt)
    
    def calc_age(self, reference_date: Optional['PdvmDateTime'] = None) -> int:
        """
        Berechnet Alter in Jahren (tagesgenau).
        Analog zur Desktop-Version calc_alter().
        
        Args:
            reference_date: Stichtag (default: heute)
            
        Returns:
            int: Alter in Jahren
        """
        if reference_date is None:
            reference_date = PdvmDateTime().now()
        
        st_int = int(reference_date.pdvm_datetime)
        date_int = int(self.pdvm_datetime)
        diff = st_int - date_int
        
        return (diff - (diff % 1000)) // 1000


# Globale Hilfsfunktionen (kompatibel mit pdvm_time.py API und Desktop-Version)

def datetime_to_pdvm(dt: datetime) -> float:
    """
    Konvertiert Python datetime in PDVM-Format.
    
    Args:
        dt: Python datetime-Objekt
        
    Returns:
        float: PDVM-Zeitstempel
    """
    pdt = PdvmDateTime()
    pdt.from_datetime(dt)
    return pdt.pdvm_datetime


def pdvm_to_datetime(pdvm: float) -> datetime:
    """
    Konvertiert PDVM-Format in Python datetime.
    
    Args:
        pdvm: PDVM-Zeitstempel
        
    Returns:
        datetime: Python datetime-Objekt
    """
    pdt = PdvmDateTime()
    pdt.pdvm_datetime = pdvm
    return pdt.to_datetime()


def now_pdvm() -> float:
    """
    Gibt aktuelle Zeit im PDVM-Format zurück.
    
    Returns:
        float: Aktueller PDVM-Zeitstempel
    """
    return datetime_to_pdvm(datetime.now())


def now_pdvm_str() -> str:
    """
    Gibt aktuelle Zeit als formatierten PDVM-String zurück (5 Dezimalstellen).
    ZENTRALE String-Formatierung.
    
    Returns:
        str: Aktueller PDVM-Zeitstempel als String
    """
    pdt = PdvmDateTime()
    pdt.now()
    return pdt.pdvm_datetime_str


def pdvm_format_display(pdvm: float) -> str:
    """
    Formatiert PDVM-Zeitstempel für Anzeige.
    
    Args:
        pdvm: PDVM-Zeitstempel
        
    Returns:
        str: Formatierter String (DD.MM.YYYY HH:MM)
    """
    pdt = PdvmDateTime()
    pdt.pdvm_datetime = pdvm
    return f"{pdt.day:02d}.{pdt.month:02d}.{pdt.year} {pdt.time_short}"


def pdvm_to_str(pdvm: float) -> str:
    """
    Konvertiert PDVM float in formatierten String (5 Dezimalstellen).
    ZENTRALE String-Formatierung für konsistente Speicherung.
    
    Args:
        pdvm: PDVM-Zeitstempel
        
    Returns:
        str: PDVM als String mit 5 Dezimalstellen
        
    Beispiel:
        >>> pdvm_to_str(2025356.15203)
        '2025356.15203'
        >>> pdvm_to_str(2025001.0)
        '2025001.00000'
    """
    pdt = PdvmDateTime()
    pdt.pdvm_datetime = pdvm
    return pdt.pdvm_datetime_str


def pdvm_add_days(pdvm: float, days: int) -> float:
    """
    Addiert Tage zu PDVM-Zeitstempel.
    
    Args:
        pdvm: PDVM-Zeitstempel
        days: Anzahl Tage
        
    Returns:
        float: Neuer PDVM-Zeitstempel
    """
    pdt = PdvmDateTime()
    pdt.pdvm_datetime = pdvm
    pdt.add_days(days)
    return pdt.pdvm_datetime


# Desktop-kompatible Funktionen (getFormTimeStamp, getDateTimeNow, etc.)

def get_form_timestamp(pdvm: float, form_country: str = 'DEU') -> str:
    """
    PDVM Datum/Zeit formatiert ausgeben (Desktop-kompatibel).
    
    Args:
        pdvm: PDVM-Zeitstempel
        form_country: Länderformat (DIN, DEU, ENG, USA)
        
    Returns:
        str: Formatierter Zeitstempel
    """
    pdt = PdvmDateTime(form_country)
    pdt.pdvm_datetime = pdvm
    return pdt.timestamp


def get_form_date(pdvm: float, form_country: str = 'DEU') -> str:
    """
    PDVM Datum formatiert ausgeben (Desktop-kompatibel).
    
    Args:
        pdvm: PDVM-Zeitstempel
        form_country: Länderformat (DIN, DEU, ENG, USA)
        
    Returns:
        str: Formatiertes Datum
    """
    pdt = PdvmDateTime(form_country)
    pdt.pdvm_datetime = pdvm
    return pdt.date


def get_form_time(pdvm: float, form_country: str = 'DEU') -> str:
    """
    PDVM Zeit formatiert ausgeben (Desktop-kompatibel).
    
    Args:
        pdvm: PDVM-Zeitstempel
        form_country: Länderformat (DIN, DEU, ENG, USA)
        
    Returns:
        str: Formatierte Zeit
    """
    pdt = PdvmDateTime(form_country)
    pdt.pdvm_datetime = pdvm
    return pdt.time


def get_datetime_now() -> float:
    """
    Aktueller Zeitpunkt (Desktop-kompatibel).
    
    Returns:
        float: Aktueller PDVM-Zeitstempel
    """
    return now_pdvm()


def get_a_year() -> int:
    """
    Aktuelles Jahr (Desktop-kompatibel).
    
    Returns:
        int: Aktuelles Jahr
    """
    return datetime.now().year


# Hilfsklass für Class Properties (Desktop PdvmDateTimeUtils)

class PdvmDateTimeUtilsMeta(type):
    """Metaclass für PdvmDateTimeUtils um Class Properties zu ermöglichen."""
    
    @property
    def PdvmDateTimeNow(cls) -> float:
        """Property: Aktueller PDVM-Zeitstempel als float."""
        return now_pdvm()
    
    @property  
    def PdvmDateNow(cls) -> float:
        """Property: Aktuelles Datum als float (ohne Zeit)."""
        pdt = PdvmDateTime()
        pdt.now()
        return float(pdt.pdvm_date)
    
    @property
    def PdvmTimeNow(cls) -> float:
        """Property: Aktuelle Zeit als float (Dezimalanteil des Tages)."""
        pdt = PdvmDateTime()
        pdt.now()
        return pdt.pdvm_time
    
    @property
    def PdvmDateTimeNowStr(cls) -> str:
        """Property: Aktuelle DateTime als formatierter String (5 Dezimalstellen)."""
        return now_pdvm_str()
    
    @property
    def PdvmDateNowStr(cls) -> str:
        """Property: Aktuelles Datum als formatierter String (00:00:00.000)."""
        pdt = PdvmDateTime()
        pdt.now()
        # Nur Datum, Zeit auf 0 setzen
        pdt.pdvm_datetime = float(pdt.pdvm_date)
        return pdt.pdvm_datetime_str
    
    @property
    def PdvmTimeNowStr(cls) -> str:
        """Property: Aktuelle Zeit als formatierter String."""
        pdt = PdvmDateTime()
        pdt.now()
        # Nur Zeit-Komponente
        time_dt = PdvmDateTime()
        time_dt.pdvm_datetime = pdt.pdvm_time
        return time_dt.pdvm_datetime_str


class PdvmDateTimeUtils(metaclass=PdvmDateTimeUtilsMeta):
    """
    Zentrale Utilities-Klasse für PDVM-DateTime-Werte mit Class Properties.
    Kompatibel mit Desktop-Version.
    
    Keine Instanziierung erforderlich - direkter Zugriff via Properties:
    
    Properties:
      - PdvmDateTimeNow     → float (voller PDVM-Zeitstempel)
      - PdvmDateNow         → float (nur Datum, Zeitanteil = 0)
      - PdvmTimeNow         → float (nur Zeitanteil als Bruchteil eines Tages)
      - PdvmDateTimeNowStr  → str (zentrale String-Formatierung mit 5 Dezimalstellen)
      - PdvmDateNowStr      → str (Datum als String mit .00000)
      - PdvmTimeNowStr      → str (Zeit als String mit 5 Dezimalstellen)
    
    Verwendung:
        zeitstempel = PdvmDateTimeUtils.PdvmDateTimeNow
        string_format = PdvmDateTimeUtils.PdvmDateTimeNowStr
    """
    pass


# Hauptprogramm - Testumgebung
if __name__ == '__main__':
    print("=" * 70)
    print("PDVM DateTime - Testausgabe")
    print("=" * 70)
    
    # Test 1: Aktuelle Zeit
    pdt = PdvmDateTime()
    pdt.now()
    
    print(f"\n1. Aktuelle Zeit:")
    print(f"   PDVM DateTime:     {pdt.pdvm_datetime}")
    print(f"   PDVM String (5 D): {pdt.pdvm_datetime_str}")
    print(f"   Formatiert (DEU):  {pdt.timestamp}")
    print(f"   Display:           {pdvm_format_display(pdt.pdvm_datetime)}")
    
    # Test 2: Verschiedene Formate
    print(f"\n2. Verschiedene Länderformate:")
    for country in ['DIN', 'DEU', 'ENG', 'USA']:
        pdt2 = PdvmDateTime(country)
        pdt2.now()
        print(f"   {country}: {pdt2.date} - {pdt2.time}")
    
    # Test 3: Kalenderberechnungen
    print(f"\n3. Kalenderberechnungen:")
    print(f"   Jahr:              {pdt.year}")
    print(f"   Monat:             {pdt.month}")
    print(f"   Tag:               {pdt.day}")
    print(f"   Tag im Jahr:       {pdt.yday}")
    print(f"   Wochentag:         {pdt.weekday} (0=Mo, 6=So)")
    print(f"   Schaltjahr:        {pdt.is_leap_year}")
    print(f"   Periode (YYYYMM):  {pdt.period}")
    print(f"   Erster Tag Monat:  {pdt.first_day_of_month}")
    print(f"   Letzter Tag Monat: {pdt.last_day_of_month}")
    
    # Test 4: Arithmetik
    print(f"\n4. Arithmetische Operationen:")
    base_time = pdt.pdvm_datetime
    print(f"   Basis:             {pdvm_format_display(base_time)}")
    
    pdt.add_days(7)
    print(f"   +7 Tage:           {pdvm_format_display(pdt.pdvm_datetime)}")
    
    pdt.pdvm_datetime = base_time
    pdt.add_months(1)
    print(f"   +1 Monat:          {pdvm_format_display(pdt.pdvm_datetime)}")
    
    pdt.pdvm_datetime = base_time
    pdt.add_years(1)
    print(f"   +1 Jahr:           {pdvm_format_display(pdt.pdvm_datetime)}")
    
    # Test 5: Altersberechnung
    print(f"\n5. Altersberechnung:")
    birthdate = PdvmDateTime()
    birthdate.from_datetime(datetime(1990, 5, 15))
    age = birthdate.calc_age()
    print(f"   Geburtsdatum:      {birthdate.date}")
    print(f"   Alter:             {age} Jahre")
    
    # Test 6: PdvmDateTimeUtils Class Properties
    print(f"\n6. PdvmDateTimeUtils Class Properties:")
    print(f"   PdvmDateTimeNow:    {PdvmDateTimeUtils.PdvmDateTimeNow}")
    print(f"   PdvmDateTimeNowStr: {PdvmDateTimeUtils.PdvmDateTimeNowStr}")
    print(f"   PdvmDateNow:        {PdvmDateTimeUtils.PdvmDateNow}")
    print(f"   PdvmDateNowStr:     {PdvmDateTimeUtils.PdvmDateNowStr}")
    
    # Test 7: Zentrale String-Formatierung
    print(f"\n7. Zentrale String-Formatierung:")
    test_values = [
        2025001.0,          # Neujahr ohne Zeit
        2025001.120000,     # Neujahr 12:00:00
        2025356.152032,     # 22.12.2025 15:20:32
    ]
    for val in test_values:
        str_formatted = pdvm_to_str(val)
        display = pdvm_format_display(val)
        print(f"   {val:15.6f} → '{str_formatted}' → {display}")
    
    print("\n" + "=" * 70)
    print("✅ Alle Tests erfolgreich!")
    print("=" * 70)
