import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { apiClient, menuAPI } from '../api/client'
import MandantCreate from './MandantCreate'
import MandantSetup from './MandantSetup'
import './Dashboard.css'

interface DashboardProps {
  onLogout: () => void
  mandantId: string
  token: string
}

interface MenuItem {
  id: string
  label: string
  icon?: string
  table?: string
  action?: string
  type?: string
}

interface MenuData {
  verticalMenu: MenuItem[]
  grundMenu: MenuItem[]
}

export default function Dashboard({ onLogout, mandantId, token }: DashboardProps) {
  const [menuData, setMenuData] = useState<MenuData>({ verticalMenu: [], grundMenu: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showGrundMenu, setShowGrundMenu] = useState(false)
  const [showMandantCreate, setShowMandantCreate] = useState(false)
  const [showMandantSetup, setShowMandantSetup] = useState(false)

  useEffect(() => {
    loadMenu()
  }, [])

  async function loadMenu() {
    try {
      setLoading(true)
      setError(null)
      
      const token = localStorage.getItem('token')
      const response = await apiClient.get('/menu/user/start', {
        headers: { Authorization: `Bearer ${token}` }
      })
      const menuData = response.data
      
      console.log('Menü geladen:', menuData)
      
      // Menü-Struktur parsen
      const verticalItems: MenuItem[] = []
      const grundItems: MenuItem[] = []
      
      // Icon-Mapping für verschiedene Bereiche
      const iconMap: Record<string, string> = {
        'PERSONALWESEN': '👥',
        'FINANZWESEN': '💰',
        'BENUTZERDATEN': '👤',
        'ADMINISTRATION': '⚙️',
        'TESTBEREICH': '🧪'
      }
      
      // VERTIKAL-Menü extrahieren (Hauptnavigation mit App-Links)
      if (menuData.menu_data?.VERTIKAL) {
        Object.entries(menuData.menu_data.VERTIKAL).forEach(([key, value]: [string, any]) => {
          // Nur BUTTON-Typen anzeigen (keine Separatoren)
          if (value.type === 'BUTTON' && value.visible && !value.parent_guid) {
            const appName = value.command?.params?.app_name
            verticalItems.push({
              id: key,
              label: value.label,
              icon: iconMap[appName] || '📁',
              action: value.command?.handler,
              table: appName,
              type: value.type
            })
          }
        })
      }
      
      // GRUND-Menü extrahieren (Basis-Funktionen)
      let basisSubmenuId: string | null = null
      if (menuData.menu_data?.GRUND) {
        // Erst das Basis-SUBMENU finden
        Object.entries(menuData.menu_data.GRUND).forEach(([key, value]: [string, any]) => {
          if (value.type === 'SUBMENU' && value.label === 'Basis' && !value.parent_guid) {
            basisSubmenuId = key
          }
        })
        
        // Dann die Kinder des Basis-SUBMENU sammeln
        if (basisSubmenuId) {
          Object.entries(menuData.menu_data.GRUND).forEach(([key, value]: [string, any]) => {
            if (value.type === 'BUTTON' && value.visible && value.parent_guid === basisSubmenuId) {
              grundItems.push({
                id: key,
                label: value.label,
                icon: value.icon || '•',
                action: value.command?.handler,
                type: value.type
              })
            }
          })
        }
      }
      
      console.log('GRUND Items gefunden:', grundItems)
      console.log('VERTIKAL Items gefunden:', verticalItems)
      
      // Nach sort_order sortieren
      verticalItems.sort((a, b) => {
        const aData = menuData.menu_data?.VERTIKAL?.[a.id]
        const bData = menuData.menu_data?.VERTIKAL?.[b.id]
        return (aData?.sort_order || 0) - (bData?.sort_order || 0)
      })
      
      grundItems.sort((a, b) => {
        const aData = menuData.menu_data?.GRUND?.[a.id]
        const bData = menuData.menu_data?.GRUND?.[b.id]
        return (aData?.sort_order || 0) - (bData?.sort_order || 0)
      })
      
      setMenuData({ verticalMenu: verticalItems, grundMenu: grundItems })
    } catch (err: any) {
      console.error('Fehler beim Laden des Menüs:', err)
      setError(err.response?.data?.detail || 'Menü konnte nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="dashboard-container">
      <header className="dashboard-header-wrapper">
        <div className="dashboard-header-top">
          <h1 className="dashboard-title">PDVM System</h1>
          <div className="dashboard-mandant-info">
            <span style={{color: '#666', fontSize: '0.9rem'}}>Mandant: {mandantId.substring(0, 8)}...</span>
          </div>
          <div className="dashboard-header-actions">
            <button
              onClick={() => setShowMandantCreate(true)}
              className="dashboard-menu-button"
              style={{ marginRight: '0.5rem', backgroundColor: '#28a745' }}
            >
              Neuer Mandant
            </button>
            <button
              onClick={() => setShowMandantSetup(true)}
              className="dashboard-menu-button"
              style={{ marginRight: '1rem', backgroundColor: '#007bff' }}
            >
              Mandant aufbauen
            </button>
            {!loading && menuData.grundMenu.length > 0 && (
              <>
                <button 
                  onClick={() => setShowGrundMenu(!showGrundMenu)} 
                  className="dashboard-menu-button"
                >
                  Basis ▾
                </button>
                {showGrundMenu && (
                  <div className="dashboard-dropdown">
                    {menuData.grundMenu.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => {
                          if (item.action === 'logout') onLogout()
                          setShowGrundMenu(false)
                        }}
                        className="dashboard-dropdown-item"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        
        {/* Vertikales Menü (Hauptnavigation) */}
        {!loading && menuData.verticalMenu.length > 0 && (
          <nav className="dashboard-nav">
            {menuData.verticalMenu.map((item) => (
              <Link
                key={item.id}
                to={item.table ? `/app/${item.table}` : '#'}
                className="dashboard-nav-link"
              >
                <span className="dashboard-nav-icon">{item.icon}</span>
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      </header>
      
      <main className="dashboard-main">
        {loading && <p className="dashboard-loading-text">Menü wird geladen...</p>}
        
        {error && <p className="dashboard-error-text">{error}</p>}
        
        {showMandantCreate ? (
          <MandantCreate
            token={token}
            onSuccess={() => {
              setShowMandantCreate(false)
              alert('Mandant gespeichert')
            }}
            onCancel={() => setShowMandantCreate(false)}
          />
        ) : showMandantSetup ? (
          <MandantSetup
            token={token}
            onSuccess={() => {
              setShowMandantSetup(false)
              alert('Mandanten-Datenbank erfolgreich aufgebaut')
            }}
            onCancel={() => setShowMandantSetup(false)}
          />
        ) : (
          !loading && !error && (
            <div className="dashboard-content">
              <h2 className="dashboard-welcome-title">Willkommen im PDVM System</h2>
              <p className="dashboard-welcome-text">
                Wählen Sie einen Bereich aus der Navigation oben.
              </p>
            </div>
          )
        )}
      </main>
    </div>
  )
}
