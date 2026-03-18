"""
Core Service für Control Dictionary Template-Handling

Implementiert:
1. Template-Loading aus 666666... (Basis) und 555555... (Modul-spezifisch)
2. Template-Merge für neue Controls
3. MODUL_TYPE Switching mit Daten-Mapping
"""

from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
import copy


def _table_prefix(table_name: str) -> str:
    table = str(table_name or '').strip()
    if not table:
        return 'SYS'
    if '_' in table:
        return table.split('_', 1)[0].upper()
    return table[:3].upper() or 'CTL'


def _canonical_control_name(table_name: str, field_name: str) -> str:
    prefix = _table_prefix(table_name)
    field = str(field_name or '').strip().upper()
    if not field:
        return prefix
    return f"{prefix}_{field}"


class ControlTemplateService:
    """Service für Control Template Operationen"""
    
    # Template GUIDs
    TEMPLATE_BASE = UUID('66666666-6666-6666-6666-666666666666')
    TEMPLATE_MODUL = UUID('55555555-5555-5555-5555-555555555555')
    
    def __init__(self, db_connection, template_555_data: Optional[Dict[str, Any]] = None):
        self.db = db_connection
        self._template_555_data = copy.deepcopy(template_555_data) if isinstance(template_555_data, dict) else None

    async def _load_template_555_data(self) -> Dict[str, Any]:
        if isinstance(self._template_555_data, dict):
            return copy.deepcopy(self._template_555_data)

        result = await self.db.fetchrow(
            'SELECT daten FROM sys_control_dict WHERE uid = $1',
            self.TEMPLATE_MODUL
        )
        if not result:
            raise ValueError("Modul-Template 555555... nicht gefunden")

        data = result['daten']
        if isinstance(data, str):
            import json
            data = json.loads(data)
        if not isinstance(data, dict):
            raise ValueError("Modul-Template 'daten' ist kein JSON-Objekt")
        return data

    async def load_control_defaults(self, modul_type: str) -> Dict[str, Any]:
        modul_norm = str(modul_type or '').strip().lower()
        if modul_norm not in ['edit', 'view', 'tabs']:
            raise ValueError(f"Ungültiger modul_type: {modul_type}")

        template_data = await self._load_template_555_data()

        defaults: Dict[str, Any] = {}
        templates = template_data.get('TEMPLATES')
        if isinstance(templates, dict):
            tpl_control = templates.get('CONTROL')
            if isinstance(tpl_control, dict):
                defaults.update(copy.deepcopy(tpl_control))

        modul_section = template_data.get('MODUL')
        if isinstance(modul_section, dict):
            ci = {str(k).strip().lower(): k for k in modul_section.keys()}
            key = ci.get(modul_norm)
            if key is not None and isinstance(modul_section.get(key), dict):
                defaults.update(copy.deepcopy(modul_section[key]))

        defaults['modul_type'] = modul_norm
        return defaults

    async def resolve_effective_control_data(self, stored_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(stored_data, dict):
            return {}
        modul_type = str(stored_data.get('modul_type') or '').strip().lower()
        if not modul_type:
            return dict(stored_data)

        defaults = await self.load_control_defaults(modul_type)
        effective = copy.deepcopy(defaults)
        effective.update(stored_data)
        return effective

    async def normalize_control_for_storage(self, effective_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(effective_data, dict):
            return {}
        modul_type = str(effective_data.get('modul_type') or '').strip().lower()
        if not modul_type:
            return dict(effective_data)

        defaults = await self.load_control_defaults(modul_type)
        overrides = {}
        for key, value in effective_data.items():
            if key not in defaults or defaults.get(key) != value:
                overrides[key] = value
        overrides['modul_type'] = modul_type
        return overrides
    
    async def load_base_template(self) -> Dict[str, Any]:
        """
        Lädt Basis-Template (666666...)
        
        Returns:
            Dict mit ROOT und CONTROL Struktur
        """
        result = await self.db.fetchrow(
            'SELECT daten FROM sys_control_dict WHERE uid = $1',
            self.TEMPLATE_BASE
        )
        
        if not result:
            raise ValueError("Basis-Template 666666... nicht gefunden")
        
        # Parse JSON wenn String
        data = result['daten']
        if isinstance(data, str):
            import json
            data = json.loads(data)
        
        return data
    
    async def load_modul_template(self, modul_type: str) -> Dict[str, Any]:
        """
        Lädt Modul-spezifisches Template aus 555555...
        
        Args:
            modul_type: 'edit', 'view' oder 'tabs'
        
        Returns:
            Dict mit Modul-spezifischer Struktur
        """
        if modul_type not in ['edit', 'view', 'tabs']:
            raise ValueError(f"Ungültiger modul_type: {modul_type}")
        
        template_data = await self._load_template_555_data()
        
        # Hole MODUL[modul_type]
        if 'MODUL' not in template_data or modul_type not in template_data['MODUL']:
            raise ValueError(f"Modul-Template für {modul_type} nicht gefunden")
        
        return template_data['MODUL'][modul_type]
    
    def merge_templates(
        self, 
        base_template: Dict[str, Any],
        modul_template: Dict[str, Any],
        modul_type: str
    ) -> Dict[str, Any]:
        """
        Merged Basis-Template mit Modul-Template
        
        Args:
            base_template: Template 666666... (ROOT + CONTROL)
            modul_template: Template aus 555555...MODUL[type]
            modul_type: edit/view/tabs
        
        Returns:
            Merged Struktur für neues Control
        """
        # Deep copy um Originale nicht zu verändern
        merged = copy.deepcopy(modul_template)
        
        # MODUL aus CONTROL.MODUL in Hauptstruktur einfügen
        if 'CONTROL' in base_template and 'MODUL' in base_template['CONTROL']:
            # CONTROL.MODUL durch gewählten Typ ersetzen
            # (wird dann durch Backend-Logik aufgelöst)
            pass
        
        # Sicherstellen dass modul_type gesetzt ist
        merged['modul_type'] = modul_type
        
        return merged
    
    async def create_new_control(
        self,
        modul_type: str,
        table_prefix: str,
        field_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Erstellt neues Control basierend auf Templates
        
        Args:
            modul_type: edit/view/tabs
            table_prefix: z.B. 'sys_' für sys_control_dict
            field_data: Zusätzliche Felddaten vom User
        
        Returns:
            Komplettes Control-Dict bereit für Insert
        """
        # Templates laden
        base_template = await self.load_base_template()
        modul_template = await self.load_modul_template(modul_type)
        
        # Merge
        control_data = self.merge_templates(base_template, modul_template, modul_type)
        
        # User-Daten anwenden wenn vorhanden
        if field_data:
            control_data.update(field_data)
        
        # NAME/SELF_NAME immer aus TABLE + FIELD ableiten (linear, einheitlich)
        table_name = str(control_data.get('table') or '').strip()
        field_name = str(
            control_data.get('field')
            or control_data.get('feld')
            or control_data.get('name')
            or ''
        ).strip().upper()
        canonical_name = _canonical_control_name(table_name, field_name)
        if field_name:
            control_data['field'] = field_name
            control_data['feld'] = field_name
        control_data['name'] = canonical_name
        control_data['SELF_NAME'] = canonical_name
        
        # UUID generieren
        new_uid = uuid4()
        
        return {
            'uid': new_uid,
            'name': control_data.get('SELF_NAME', ''),
            'daten': control_data,
            'historisch': 0
        }
    
    def map_fields_on_modul_change(
        self,
        old_data: Dict[str, Any],
        old_modul: str,
        new_modul: str
    ) -> Dict[str, Any]:
        """
        Mapped Daten beim Wechsel des MODUL_TYPE
        
        Logik:
        - Gemeinsame Felder bleiben erhalten
        - Alte spezifische Felder werden gelöscht
        - Neue spezifische Felder werden mit Defaults hinzugefügt
        
        Args:
            old_data: Aktuelle Control-Daten
            old_modul: Alter modul_type
            new_modul: Neuer modul_type
        
        Returns:
            Gemappte Daten mit neuem modul_type
        """
        # Gemeinsame Felder über alle Modul-Typen
        common_fields = {
            'name', 'type', 'label', 'table', 'gruppe', 'feld',
            'SELF_NAME', 'parent_guid', 'display_order', 'configs'
        }
        
        # Modul-spezifische Felder
        modul_fields = {
            'edit': {
                'read_only', 'abdatum', 'historical', 'source_path'
            },
            'view': {
                'show', 'sortable', 'searchable', 'filterType',
                'sortDirection', 'sortByOriginal', 'expert_mode',
                'expert_order', 'control_type', 'default', 'dropdown'
            },
            'tabs': {
                'element_fields', 'element_frame_guid', 'read_only'
            }
        }
        
        # Neue Daten mit gemeinsamen Feldern
        new_data = {}
        for field in common_fields:
            if field in old_data:
                new_data[field] = old_data[field]
        
        # modul_type setzen
        new_data['modul_type'] = new_modul
        
        # Modul-spezifische Felder aus altem Typ die auch im neuen existieren
        old_specific = modul_fields.get(old_modul, set())
        new_specific = modul_fields.get(new_modul, set())
        
        # Übernehme gemeinsame spezifische Felder (z.B. read_only bei edit→tabs)
        for field in old_specific & new_specific:
            if field in old_data:
                new_data[field] = old_data[field]
        
        return new_data
    
    async def apply_modul_template_defaults(
        self,
        control_data: Dict[str, Any],
        modul_type: str
    ) -> Dict[str, Any]:
        """
        Fügt fehlende Felder aus Modul-Template hinzu
        
        Args:
            control_data: Aktuelle (möglicherweise unvollständige) Daten
            modul_type: edit/view/tabs
        
        Returns:
            Vollständige Daten mit allen Template-Defaults
        """
        # Template laden
        modul_template = await self.load_modul_template(modul_type)
        
        # Merge: Template-Defaults + bestehende Daten (bestehende überschreiben)
        result = copy.deepcopy(modul_template)
        result.update(control_data)
        
        # modul_type sicherstellen
        result['modul_type'] = modul_type
        
        return result
    
    async def switch_modul_type(
        self,
        control_uid: UUID,
        new_modul_type: str
    ) -> Dict[str, Any]:
        """
        Wechselt MODUL_TYPE eines bestehenden Controls
        
        Prozess:
        1. Lade aktuelles Control
        2. Mappe Felder (alte → neue)
        3. Füge neue Template-Defaults hinzu
        4. Update in DB
        
        Args:
            control_uid: UUID des Controls
            new_modul_type: edit/view/tabs
        
        Returns:
            Aktualisierte Control-Daten
        """
        # Aktuelles Control laden
        result = await self.db.fetchrow(
            'SELECT daten FROM sys_control_dict WHERE uid = $1',
            control_uid
        )
        
        if not result:
            raise ValueError(f"Control {control_uid} nicht gefunden")
        
        # Parse JSON wenn String
        old_data = result['daten']
        if isinstance(old_data, str):
            import json
            old_data = json.loads(old_data)
        
        old_modul = old_data.get('modul_type', '')
        
        # Mapping durchführen
        mapped_data = self.map_fields_on_modul_change(old_data, old_modul, new_modul_type)
        
        # Template-Defaults anwenden
        complete_data = await self.apply_modul_template_defaults(mapped_data, new_modul_type)
        stored_data = await self.normalize_control_for_storage(complete_data)
        
        # Update in DB
        import json
        await self.db.execute("""
            UPDATE sys_control_dict
            SET daten = $1,
                modified_at = NOW()
            WHERE uid = $2
        """, json.dumps(stored_data), control_uid)
        
        return complete_data


# Convenience Functions

async def create_control(
    db_connection,
    modul_type: str,
    table_name: str,
    field_data: Dict[str, Any]
) -> UUID:
    """
    Erstellt neues Control und speichert in DB
    
    Args:
        db_connection: asyncpg Connection
        modul_type: edit/view/tabs
        table_name: Zieltabelle (für Präfix-Generierung)
        field_data: User-Daten (name, label, type, etc.)
    
    Returns:
        UUID des neuen Controls
    """
    service = ControlTemplateService(db_connection)
    
    # Tabellepräfix wird intern in create_new_control berechnet
    table_prefix = table_name.split('_')[0] + '_' if '_' in table_name else table_name[:3] + '_'
    
    # Control erstellen
    control = await service.create_new_control(modul_type, table_prefix, field_data)
    control_to_store = await service.normalize_control_for_storage(control['daten'])
    
    # In DB einfügen
    import json
    await db_connection.execute("""
        INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
    """, control['uid'], control['name'], json.dumps(control_to_store), control['historisch'])
    
    return control['uid']


async def switch_control_modul(
    db_connection,
    control_uid: UUID,
    new_modul_type: str
) -> Dict[str, Any]:
    """
    Wechselt MODUL_TYPE eines Controls
    
    Args:
        db_connection: asyncpg Connection
        control_uid: UUID des Controls
        new_modul_type: edit/view/tabs
    
    Returns:
        Aktualisierte Control-Daten
    """
    service = ControlTemplateService(db_connection)
    return await service.switch_modul_type(control_uid, new_modul_type)
