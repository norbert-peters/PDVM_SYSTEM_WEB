import { useEffect, useState } from 'react'
import { PdvmDialogModal } from '../common/PdvmDialogModal'
import { PdvmInputControl, type PdvmInputType } from '../common/PdvmInputControl'

export type PdvmDialogInfoItem = {
  key: string
  tab: number
  label: string
  tooltip?: string
  type: PdvmInputType
  value: unknown
}

export type PdvmDialogInfoTab = { index: number; head: string }

/**
 * Info-Fenster eines Dialogs: zeigt die Felder des Info-Frames (sys_framedaten) als schreibgeschuetzte
 * PdvmInputControls. Aufbau und Beschriftung stammen aus dem Frame, die Werte liefert der Dialog.
 */
export function PdvmDialogInfoModal(props: {
  open: boolean
  title: string
  tabs: PdvmDialogInfoTab[]
  items: PdvmDialogInfoItem[]
  loading?: boolean
  error?: string | null
  onClose: () => void
}) {
  const { open, title, tabs, items, loading, error, onClose } = props
  const [activeTab, setActiveTab] = useState<number>(1)

  useEffect(() => {
    if (!open) return
    setActiveTab(tabs[0]?.index ?? 1)
    // nur beim Oeffnen zuruecksetzen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const visibleItems = items.filter((item) => item.tab === activeTab)

  return (
    <PdvmDialogModal
      open={open}
      kind="info"
      title={title}
      confirmLabel="Schließen"
      error={error || null}
      onConfirm={onClose}
      onCancel={onClose}
      message={
        <div className="pdvm-dialog-info">
          {loading ? <div>Lade Info…</div> : null}

          {/* Regel 2.9: ein einzelner Tab bekommt keine Tab-Leiste */}
          {tabs.length > 1 ? (
            <div className="pdvm-tabs">
              <div className="pdvm-tabs__bar">
                <div className="pdvm-tabs__list" role="tablist" aria-label="Info-Tabs">
                  {tabs.map((tab) => (
                    <button
                      key={tab.index}
                      type="button"
                      role="tab"
                      aria-selected={activeTab === tab.index}
                      className={`pdvm-tabs__tab ${activeTab === tab.index ? 'pdvm-tabs__tab--active' : ''}`.trim()}
                      onClick={() => setActiveTab(tab.index)}
                    >
                      {tab.head}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          <div className="pdvm-dialog-info__fields">
            {visibleItems.map((item) => (
              <PdvmInputControl
                key={item.key}
                label={item.label}
                tooltip={item.tooltip}
                type={item.type}
                value={item.value}
                onChange={() => {}}
                readOnly
                selectable
              />
            ))}
          </div>
        </div>
      }
    />
  )
}
