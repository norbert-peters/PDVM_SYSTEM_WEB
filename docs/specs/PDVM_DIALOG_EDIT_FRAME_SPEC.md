# PDVM Dialog Edit Frame - Spec (V1)

## Ziel
Ein einheitlicher Edit-Rahmen fuer alle Dialog-Editoren.
Tabs und Kopfbereich bleiben stehen, nur der Editor-Inhalt scrollt.
Die Edit-Typen liefern Inhalte (Tabs/Felder), nicht das Layout.

## Grundprinzip
- Ein gemeinsamer Edit-Frame steuert das Layout.
- Edit-Typen liefern nur Daten (Tabs/FIELDS) und Inhalte.
- Keine speziellen Scroll-Loesungen pro Editor.

## Struktur
```
EditFrame
  - Header (fixed)
  - Edit-Tabs (fixed, aus ROOT.TABS / TAB_XX)
  - Content (scroll)
```

## Umsetzung in der App
- Layout in PdvmDialogPage ist zentral.
- `.pdvm-dialog__editAreaHeader` ist immer fix.
- `.pdvm-dialog__editAreaContent` ist der Scroll-Bereich.
- Import-Editor nutzt den gleichen Frame (Steps im Header, Content darunter).
- Menu-Editor nutzt den gleichen Frame (Menu-Tabs im Header, Content darunter).
- edit_json/show_json zeigen Edit-Infos im Header, Content scrollt.

## Standard-Renderer fuer FIELDS
- Tabs aus `ROOT.TABS` / `TAB_XX`.
- Fields nach `tab` filtern, Reihenfolge via `display_order`.
- Renderer fuer `type` bleibt generisch.

## Spezial-Renderer
- `edit_user`: Standard-Renderer mit Tabs.
- `import_data`: eigener Content, aber gleicher Frame.
- `edit_json`/`show_json`: eigener Content, aber gleicher Frame.
- `menu`: eigener Content, aber gleicher Frame.

## Vorgaben
- Editor darf keine eigenen Scroll-Container fuer Kopf/Tab erzeugen.
- Alle Edit-Typen muessen den gemeinsamen Frame nutzen.
- Dialogs nutzen keine nativen Browser-Dialoge (PdvmDialogModal).

## Vorteile
- Einheitliches Verhalten fuer alle Editoren.
- Weniger CSS-Sonderfaelle.
- Schnellere neue Edit-Typen.
- Stabiler UX und einfacher zu warten.

## Nachteile / Trade-offs
- Einmaliger Umbauaufwand fuer bestehende Editoren.
- Spezial-Editoren brauchen Adapter fuer den Content.
- Weniger Freiheit fuer individuelle Layouts.
