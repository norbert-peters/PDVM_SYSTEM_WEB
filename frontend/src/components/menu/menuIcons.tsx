import type { ReactNode } from 'react'
import * as LucideIcons from 'lucide-react'

export const MENU_ICON_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'Home', label: 'Home' },
  { value: 'LayoutDashboard', label: 'Dashboard' },
  { value: 'FileText', label: 'Dokument' },
  { value: 'Folder', label: 'Ordner' },
  { value: 'BookOpen', label: 'Buch' },
  { value: 'Users', label: 'Benutzer (Gruppe)' },
  { value: 'User', label: 'Benutzer' },
  { value: 'Shield', label: 'Sicherheit' },
  { value: 'Lock', label: 'Schloss' },
  { value: 'Key', label: 'Schlüssel' },
  { value: 'Settings', label: 'Einstellungen' },
  { value: 'Wrench', label: 'Werkzeug' },
  { value: 'Search', label: 'Suche' },
  { value: 'Plus', label: 'Hinzufügen' },
  { value: 'Edit', label: 'Bearbeiten' },
  { value: 'Save', label: 'Speichern' },
  { value: 'Trash2', label: 'Löschen' },
  { value: 'RefreshCcw', label: 'Aktualisieren' },
  { value: 'LogIn', label: 'Login' },
  { value: 'LogOut', label: 'Logout' },
  { value: 'Info', label: 'Info' },
  { value: 'CircleHelp', label: 'Hilfe' },
  { value: 'AlertTriangle', label: 'Warnung' },
  { value: 'Check', label: 'OK' },
  { value: 'X', label: 'Abbruch' },
  { value: 'ChevronRight', label: 'Weiter' },
  { value: 'ChevronLeft', label: 'Zurück' },
  { value: 'ChevronUp', label: 'Hoch' },
  { value: 'ChevronDown', label: 'Runter' },
  { value: 'Menu', label: 'Menü' },
  { value: 'List', label: 'Liste' },
  { value: 'Grid2x2', label: 'Kacheln' },
  { value: 'Layers', label: 'Ebenen' },
  { value: 'Database', label: 'Datenbank' },
  { value: 'Calendar', label: 'Kalender' },
  { value: 'Bell', label: 'Benachrichtigung' },
  { value: 'Mail', label: 'Mail' },
  { value: 'Phone', label: 'Telefon' },
  { value: 'Globe', label: 'Web' },
  { value: 'Printer', label: 'Drucker' },
  { value: 'Download', label: 'Download' },
  { value: 'Upload', label: 'Upload' },
]

export function normalizeIconName(value: string): string {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^[A-Za-z][A-Za-z0-9]*$/.test(raw)) return raw

  return raw
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1).toLowerCase())
    .join('')
}

export function renderMenuIcon(value: any, size = 16): ReactNode {
  const raw = String(value || '').trim()
  if (!raw) return null

  const normalized = normalizeIconName(raw)
  const Icon = (LucideIcons as any)[normalized] as any

  return (
    <span
      className="menu-icon"
      style={{ display: 'inline-flex', alignItems: 'center', color: 'currentColor', width: size, height: size }}
    >
      {Icon ? (
        <Icon
          size={size}
          strokeWidth={1.8}
          stroke="currentColor"
          color="currentColor"
          style={{ display: 'block' }}
        />
      ) : (
        raw
      )}
    </span>
  )
}
