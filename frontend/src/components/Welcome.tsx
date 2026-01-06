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
      <div style={{ marginTop: '2rem', padding: '1rem', background: '#f0f0f0', borderRadius: '8px' }}>
        <h3>System-Status</h3>
        <ul>
          <li>✅ Anmeldung erfolgreich</li>
          <li>✅ Mandant ausgewählt</li>
          <li>✅ Neues Layout aktiv</li>
        </ul>
      </div>
    </div>
  );
};

export default Welcome;
