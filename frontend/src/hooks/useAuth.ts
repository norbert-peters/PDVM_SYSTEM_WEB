import { useState, useEffect } from 'react';

export interface User {
  uid: string;
  username: string;
  name?: string;
  benutzer?: string;
  email?: string;
}

export interface Mandant {
  uid: string;
  name: string;
}

export interface AuthContextValue {
  currentUser: User | null;
  currentMandant: Mandant | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  selectMandant: (mandantUid: string) => void;
}

/**
 * Hook zur Verwaltung des Authentifizierungsstatus
 * TODO: Integration mit tatsächlichem Auth-System aus client.ts
 */
export const useAuth = (): AuthContextValue => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [currentMandant, setCurrentMandant] = useState<Mandant | null>(null);

  useEffect(() => {
    // Lade gespeicherte Auth-Daten aus localStorage
    const token = localStorage.getItem('token');
    const userDataStr = localStorage.getItem('user_data'); // Backend speichert hier user_data
    const mandantStr = localStorage.getItem('currentMandant');

    if (token && userDataStr) {
      try {
        const userData = JSON.parse(userDataStr);
        // Konvertiere user_data zu User Format
        setCurrentUser({
          uid: userData.uid || userData.benutzer_uid,
          username: userData.username || userData.benutzer,
          name: userData.name,
          benutzer: userData.benutzer,
          email: userData.email
        });
      } catch (e) {
        console.error('Failed to parse user data:', e);
      }
    }

    if (mandantStr) {
      try {
        setCurrentMandant(JSON.parse(mandantStr));
      } catch (e) {
        console.error('Failed to parse mandant data:', e);
      }
    }
  }, []);

  const login = async (username: string, password: string) => {
    // TODO: Implementierung mit echtem API Call
    console.log('Login:', username, password);
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('currentMandant');
    setCurrentUser(null);
    setCurrentMandant(null);
  };

  const selectMandant = (mandantUid: string) => {
    // TODO: Lade Mandant-Daten vom Backend
    const mandant: Mandant = { uid: mandantUid, name: 'Mandant' };
    localStorage.setItem('currentMandant', JSON.stringify(mandant));
    setCurrentMandant(mandant);
  };

  return {
    currentUser,
    currentMandant,
    isAuthenticated: !!currentUser,
    login,
    logout,
    selectMandant,
  };
};
