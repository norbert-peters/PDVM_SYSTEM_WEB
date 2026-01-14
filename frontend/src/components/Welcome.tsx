/**
 * Welcome Component
 * Einfache Willkommensseite für Startmenü
 */
import React from 'react';
import { useAuth } from '../hooks/useAuth';

interface WelcomeProps {
  mandantId: string;
}

const Welcome: React.FC<WelcomeProps> = ({ mandantId }) => {
  const { currentUser, currentMandant } = useAuth();

  return (
    <div style={{ padding: '2rem' }}>
      <h1>Willkommen im PDVM System</h1>
      <p>
        Benutzer: {currentUser?.name || currentUser?.benutzer || currentUser?.username}
      </p>
      <p>
        Mandant: {currentMandant?.name} ({mandantId})
      </p>
      <div className="surface-secondary" style={{ marginTop: '2rem', padding: '1rem', borderRadius: 'var(--border-radius-md)' }}>
        <h3>System-Status</h3>
        <ul style={{ listStyleType: 'none', paddingLeft: 0 }}>
          <li>✅ Anmeldung erfolgreich</li>
          <li>✅ Mandant ausgewählt</li>
          <li>✅ Neues Layout aktiv</li>
        </ul>
      </div>
    </div>
  );
};

export default Welcome;
