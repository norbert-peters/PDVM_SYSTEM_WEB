-- Prüfe und erstelle sys_systemsteuerung Struktur
-- Die Tabelle muss die GCS Gruppe->Feld Struktur abbilden

-- Prüfe ob Tabelle existiert
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'sys_systemsteuerung'
);

-- Zeige Struktur
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'sys_systemsteuerung'
ORDER BY ordinal_position;

-- Falls Tabelle leer ist, füge Beispieldaten hinzu
-- INSERT INTO sys_systemsteuerung (user_guid, gruppe, feld, wert, stichtag)
-- VALUES (
--     '7f7e9c5d-4e8f-4b5e-9f3c-8d7a6b5c4d3e'::uuid,  -- Beispiel user_guid
--     '3424b00f-bb4d-4759-9689-e9e08249117b',         -- menu_guid als Gruppe
--     'toggle_menu',                                   -- Feld
--     '1',                                             -- Wert (1=sichtbar)
--     NULL                                             -- Kein Stichtag
-- );

-- Zeige alle Einträge
SELECT * FROM sys_systemsteuerung;
