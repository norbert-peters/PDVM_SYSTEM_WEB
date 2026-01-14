import React, { useState, useRef, useEffect } from 'react';
import './PdvmDateTimePicker.css';

interface PdvmDateTimePickerProps {
  /**
   * Der Datumswert als ISO-8601 String (YYYY-MM-DDTHH:mm:ss).
   * Kann leer sein (null/undefined).
   */
  value: string | null | undefined;

  /**
   * Callback, der NUR gefeuert wird, wenn der Benutzer im Dialog "Übernehmen" klickt.
   */
  onChange: (newValue: string) => void;

  /**
   * Label für das Eingabefeld (optional)
   */
  label?: string;

  /**
   * Readonly-Modus (kein Popover bei Klick)
   */
  readOnly?: boolean;

  /**
   * Optional: Erlaubt das "Leeren" des Werts.
   * Wichtig: Leeren ist ebenfalls eine explizite Aktion (wie "Übernehmen").
   */
  allowClear?: boolean;

  /**
   * Steuert, wo der Clear-Button angezeigt wird.
   * - 'inside': nur ✕ im Eingabefeld
   * - 'popover': nur "Leeren" im Popover
   * - 'both': beides
   * - 'none': nirgends
   *
   * Default: 'both' (wenn allowClear=true)
   */
  clearPlacement?: 'inside' | 'popover' | 'both' | 'none';

  /**
   * Callback, der bei "Leeren" ausgeführt wird.
   * Der Parent sollte dann `value` auf null/undefined setzen.
   */
  onClear?: () => void;

  /**
   * Soll die Zeitkomponente angezeigt/editiert werden?
   * Default: true
    *
    * Hinweis: Für neue Verwendung bevorzugt `mode` nutzen.
   */
  showTime?: boolean;

    /**
    * Darstellungs-/Eingabe-Modus.
    * - 'datetime': Datum + Zeit
    * - 'date': nur Datum
    * - 'time': nur Zeit
    */
    mode?: 'datetime' | 'date' | 'time';

    /**
    * Sekunden in der Zeit-Eingabe anzeigen/erlauben.
    * Default: false
    */
    showSeconds?: boolean;

    /**
    * Millisekunden in der Zeit-Eingabe anzeigen/erlauben.
    * Default: false (impliziert showSeconds)
    */
    showMilliseconds?: boolean;

    /**
    * Zeigt einen "Jetzt" Button (setzt Datum/Zeit auf aktuelle lokale Zeit).
    * Default: true für mode='time', sonst false
    */
    showNowButton?: boolean;

  /**
   * Ausrichtung des Popovers relativ zum Eingabefeld.
   * - 'start': linksbündig (Popover beginnt an linker Kante)
   * - 'end': rechtsbündig (Popover endet an rechter Kante, öffnet nach links)
   * - 'auto': versucht Overflow zu vermeiden (Default)
   */
  popoverAlign?: 'start' | 'end' | 'auto';
}

/**
 * Wandelt ISO String in lesbares deutsches Format um
 * "2025-12-24T18:00:00" -> "24.12.2025 18:00"
 */
const formatDisplayValue = (
  isoStr: string | null | undefined,
  effectiveMode: 'datetime' | 'date' | 'time',
  showSeconds: boolean,
  showMilliseconds: boolean
): string => {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return 'Ungültiges Datum';

    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();

    if (effectiveMode === 'date') {
      return `${day}.${month}.${year}`;
    }

    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const seconds = String(d.getSeconds()).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');

    const timeBase = showSeconds || showMilliseconds
      ? `${hours}:${minutes}:${seconds}`
      : `${hours}:${minutes}`;

    const timeFull = showMilliseconds ? `${timeBase}.${ms}` : timeBase;

    if (effectiveMode === 'time') {
      return timeFull;
    }

    return `${day}.${month}.${year} ${timeFull}`;
  } catch (e) {
    return 'Fehler';
  }
};

const pad2 = (n: number) => String(n).padStart(2, '0');
const pad3 = (n: number) => String(n).padStart(3, '0');

const dateToDraftDate = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

const dateToDraftTime = (d: Date, showSeconds: boolean, showMilliseconds: boolean) => {
  const hh = pad2(d.getHours());
  const mm = pad2(d.getMinutes());
  const ss = pad2(d.getSeconds());
  const ms = pad3(d.getMilliseconds());

  if (showMilliseconds) return `${hh}:${mm}:${ss}.${ms}`;
  if (showSeconds) return `${hh}:${mm}:${ss}`;
  return `${hh}:${mm}`;
};

/**
 * PdvmDateTimePicker
 * 
 * Ein Widget zur Auswahl von Datum und Zeit.
 * Besonderheit: Änderungen werden erst wirksam (onChange), wenn explizit gespeichert wird.
 */
export const PdvmDateTimePicker: React.FC<PdvmDateTimePickerProps> = ({
  value,
  onChange,
  label,
  readOnly = false,
  allowClear = false,
  onClear,
  clearPlacement,
  showTime = true,
  mode,
  showSeconds = false,
  showMilliseconds = false,
  showNowButton,
  popoverAlign = 'auto'
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const [resolvedPopoverAlign, setResolvedPopoverAlign] = useState<'start' | 'end'>('start');
  
  // Draft State: Split Date and Time parts for HTML input types 'date' and 'time'
  // Format: "YYYY-MM-DD" and "HH:mm"
  const [draftDate, setDraftDate] = useState<string>('');
  const [draftTime, setDraftTime] = useState<string>('');

  const containerRef = useRef<HTMLDivElement>(null);

  const effectiveMode: 'datetime' | 'date' | 'time' = mode
    ? mode
    : (showTime ? 'datetime' : 'date');

  const effectiveShowMilliseconds = !!showMilliseconds;
  const effectiveShowSeconds = !!showSeconds || effectiveShowMilliseconds;
  const effectiveShowNowButton = typeof showNowButton === 'boolean'
    ? showNowButton
    : effectiveMode === 'time';

  const effectiveClearPlacement: 'inside' | 'popover' | 'both' | 'none' =
    clearPlacement ?? (allowClear ? 'both' : 'none');

  const canClear = allowClear && !readOnly && !!value && !!onClear;
  const showInlineClear = canClear && (effectiveClearPlacement === 'inside' || effectiveClearPlacement === 'both');
  const showPopoverClear = canClear && (effectiveClearPlacement === 'popover' || effectiveClearPlacement === 'both');

  // Initialisierung des Draft-States beim Öffnen
  useEffect(() => {
    if (!isOpen) return;

    const base = value ? new Date(value) : new Date();
    const d = !isNaN(base.getTime()) ? base : new Date();

    // Für konsistente Save-Serialisierung halten wir ein draftDate auch im time-mode.
    setDraftDate(dateToDraftDate(d));
    setDraftTime(dateToDraftTime(d, effectiveShowSeconds, effectiveShowMilliseconds));
  }, [isOpen, value, effectiveShowSeconds, effectiveShowMilliseconds]);

  // Click Outside Handler
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Popover Alignment (auto flip near viewport edges)
  useEffect(() => {
    if (!isOpen) return;

    if (popoverAlign === 'start' || popoverAlign === 'end') {
      setResolvedPopoverAlign(popoverAlign);
      return;
    }

    // auto
    const el = containerRef.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;

    // Keep in sync with CSS width (PdvmDateTimePicker.css)
    const POPOVER_WIDTH = 320;
    const MARGIN = 12;

    const wouldOverflowRight = rect.left + POPOVER_WIDTH > viewportWidth - MARGIN;
    const wouldOverflowLeft = rect.right - POPOVER_WIDTH < MARGIN;

    if (wouldOverflowRight && !wouldOverflowLeft) {
      setResolvedPopoverAlign('end');
    } else {
      setResolvedPopoverAlign('start');
    }
  }, [isOpen, popoverAlign]);

  const handleOpen = () => {
    if (!readOnly) setIsOpen(true);
  };

  const handleCancel = () => {
    setIsOpen(false);
  };

  const handleClear = () => {
    if (readOnly) return;
    if (!allowClear) return;
    if (!onClear) return;
    onClear();
    setIsOpen(false);
  };

  const handleSave = () => {
    if (effectiveMode !== 'time' && !draftDate) {
        // Falls kein Datum gewählt ist, könnte man auch Clearen
        // Hier: Nichts tun oder Fehler anzeigen
        return;
    }

    try {
        // Construct ISO String (timezone-naiv, ohne Z).
        // Kombiniert Datum+Zeit je nach Modus.
        const datePart = draftDate || dateToDraftDate(new Date());

        let fullStr = '';

        const rawTime = draftTime || (effectiveShowSeconds ? '00:00:00' : '00:00');
        const normalizedTime = /^\d{2}:\d{2}$/.test(rawTime) ? `${rawTime}:00` : rawTime;

        if (effectiveMode === 'date') {
          fullStr = `${datePart}T00:00:00`;
        } else {
          // time oder datetime
          fullStr = `${datePart}T${normalizedTime}`;
        }
        
        // Validate
        const d = new Date(fullStr);
        if (isNaN(d.getTime())) {
            alert('Ungültiges Datum');
            return;
        }

        // Wichtig: Nicht in UTC konvertieren (toISOString), sonst verschiebt sich die Uhrzeit.
        onChange(fullStr);
        setIsOpen(false);
    } catch (e) {
        console.error("Date construction error", e);
    }
  };

  const handleNow = () => {
    const now = new Date();
    setDraftDate(dateToDraftDate(now));
    setDraftTime(dateToDraftTime(now, effectiveShowSeconds, effectiveShowMilliseconds));
  };

  const displayString = formatDisplayValue(value, effectiveMode, effectiveShowSeconds, effectiveShowMilliseconds);

  const timeStep = effectiveShowMilliseconds ? 0.001 : (effectiveShowSeconds ? 1 : 60);

  return (
    <div className="pdvm-datetime-picker" ref={containerRef}>
      {/* Input / Display Field */}
      <div 
        className={`pdvm-datetime-input-wrapper ${readOnly ? 'readonly' : ''}`}
        onClick={handleOpen}
        title={label}
      >
        <span className="pdvm-datetime-text">
          {displayString || <span style={{color: '#999'}}>{label || 'Datum wählen...'}</span>}
        </span>

        {showInlineClear && (
          <button
            type="button"
            className="pdvm-datetime-clear-btn"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleClear();
            }}
            aria-label="Wert leeren"
            title="Leeren"
          >
            ✕
          </button>
        )}

        <span className="pdvm-datetime-icon">
             📅
        </span>
      </div>

      {/* Popover */}
      {isOpen && (
        <div
          className={
            `pdvm-datetime-popover ${resolvedPopoverAlign === 'end' ? 'pdvm-datetime-popover--end' : 'pdvm-datetime-popover--start'}`
          }
        >
          <div className="pdvm-datetime-header">
            {label || (effectiveMode === 'date' ? 'Datum ändern' : effectiveMode === 'time' ? 'Zeit ändern' : 'Datum & Zeit ändern')}
          </div>
          
          <div className="pdvm-datetime-content">
             {/* Native HTML5 Date Picker inside the custom popover */}
             {effectiveMode !== 'time' && (
               <div className="pdvm-datetime-field-group">
                  <label className="pdvm-datetime-field-label">Datum</label>
                  <input 
                      type="date" 
                      className="pdvm-datetime-native-input"
                      value={draftDate}
                      onChange={(e) => setDraftDate(e.target.value)}
                  />
               </div>
             )}

             {effectiveMode !== 'date' && (
                <div className="pdvm-datetime-field-group">
                    <label className="pdvm-datetime-field-label">Uhrzeit</label>
                    <input 
                        type="time" 
                        className="pdvm-datetime-native-input"
                        value={draftTime}
                        onChange={(e) => setDraftTime(e.target.value)}
                        step={timeStep}
                    />
                </div>
             )}
          </div>

          <div className="pdvm-datetime-footer">
            {effectiveShowNowButton && (
              <button className="pdvm-btn pdvm-btn-now" onClick={handleNow}>
                Jetzt
              </button>
            )}
            {showPopoverClear && (
              <button className="pdvm-btn pdvm-btn-clear" onClick={handleClear}>
                Leeren
              </button>
            )}
            <button className="pdvm-btn pdvm-btn-cancel" onClick={handleCancel}>
                Abbrechen
            </button>
            <button className="pdvm-btn pdvm-btn-save" onClick={handleSave}>
                Übernehmen
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
