import React, { useEffect, useState } from 'react';
import { PdvmDateTimePicker } from '../common/PdvmDateTimePicker';
import { gcsAPI } from '../../api/client';

export const StichtagsBar: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Angezeigter (angewendeter) Stichtag
  const [appliedIso, setAppliedIso] = useState<string | null>(null);
  const [appliedDisplay, setAppliedDisplay] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const res = await gcsAPI.getStichtag();
        if (cancelled) return;
        setAppliedIso(res.iso);
        setAppliedDisplay(res.display || '');
        setError(null);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message || 'Stichtag konnte nicht geladen werden');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleStichtagChange = async (newIso: string) => {
    try {
      setLoading(true);
      const res = await gcsAPI.setStichtagIso(newIso);
      setAppliedIso(res.iso);
      setAppliedDisplay(res.display || '');
      setError(null);

      // Globales Signal für Views (z.B. TableView) zum Refresh.
      window.dispatchEvent(
        new CustomEvent('pdvm:stichtag-changed', {
          detail: { stichtag: res.stichtag, iso: res.iso },
        })
      );
    } catch (e: any) {
      setError(e?.message || 'Stichtag konnte nicht gespeichert werden');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stichtags-bar" aria-busy={loading}>
      <div className="stichtags-bar-left">
        <span className="stichtags-bar-label">Angewendeter Stichtag:</span>
        <span className="stichtags-bar-value">
          {loading ? 'Lade…' : (appliedDisplay || '—')}
        </span>
      </div>

      <div className="stichtags-bar-right">
        <PdvmDateTimePicker
          value={appliedIso}
          onChange={handleStichtagChange}
          showTime={true}
          label="Stichtag ändern"
          readOnly={loading}
          popoverAlign="end"
        />
      </div>

      {error && (
        <div className="stichtags-bar-error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
};
