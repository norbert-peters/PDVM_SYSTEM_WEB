import { useMenu } from '../../contexts/MenuContext';

export default function MenuHome() {
  const menu = useMenu();

  const menuName =
    menu.currentMenu?.ROOT?.NAME ||
    menu.currentApp ||
    (menu.currentMenu ? 'Menü' : null);

  const isNoPermission = !menu.currentMenu && !!menu.currentApp;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ margin: '0 0 12px 0' }}>
        {isNoPermission ? 'Keine Berechtigung' : 'Willkommen'}
        {menuName ? `: ${menuName}` : ''}
      </h1>

      {isNoPermission ? (
        <div>
          <p>
            Für das Menü <strong>{menu.currentApp}</strong> liegt keine Berechtigung vor.
          </p>
          <p>Bitte ein anderes Menü auswählen oder Admin kontaktieren.</p>
        </div>
      ) : (
        <div>
          <p>
            Bitte wählen Sie links (vertikal) oder oben (horizontal) einen Menüpunkt aus.
          </p>
          <p>
            Hinweis: Beim Wechsel des Menüs wird immer diese Startseite angezeigt, damit keine
            „alte“ Auswahl stehen bleibt.
          </p>
        </div>
      )}
    </div>
  );
}