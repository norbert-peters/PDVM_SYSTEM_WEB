import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

export interface User {
  uid: string;
  username: string;
  name?: string;
  vorname?: string;
  nachname?: string;
  modeName?: string;
  benutzer?: string;
  email?: string;
}

export interface Mandant {
  uid: string;
  name: string;
  town?: string;
  street?: string;
}

export interface AuthContextValue {
  token: string | null;
  currentUser: User | null;
  currentMandant: Mandant | null;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
  selectMandant: (mandant: Mandant) => void;
  mandantId: string | null;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function parseUserFromStoredUserData(userData: any): User {
  const userNode = userData?.USER ?? {};
  const settingsNode = userData?.SETTINGS ?? {};

  const vorname: string | undefined = userNode?.VORNAME ?? userData?.vorname;
  const nachname: string | undefined = userNode?.NAME ?? userData?.nachname;
  const modeName: string | undefined = settingsNode?.MODE_NAME ?? userData?.modeName;

  return {
    uid: userData.uid || userData.benutzer_uid,
    username: userData.username || userData.benutzer,
    // legacy / fallback
    name: userData.name,
    vorname,
    nachname,
    modeName,
    benutzer: userData.benutzer,
    email: userData.email,
  };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [currentMandant, setCurrentMandant] = useState<Mandant | null>(null);

  // Initialize from LocalStorage
  useEffect(() => {
    // Restore User
    const userDataStr = localStorage.getItem('user_data');
    if (userDataStr) {
      try {
        const userData = JSON.parse(userDataStr);
        setCurrentUser(parseUserFromStoredUserData(userData));
      } catch (e) {
        console.error('Failed to parse user data', e);
      }
    }

    // Restore Mandant
    const mandantStr = localStorage.getItem('currentMandant');
    const mandantId = localStorage.getItem('mandant_id');
    if (mandantStr && mandantId) {
      try {
        const m = JSON.parse(mandantStr);
        if (m.uid === mandantId) {
          setCurrentMandant(m);
        }
      } catch (e) {
        console.error('Failed to parse mandant data', e);
      }
    }
  }, []);

  const login = useCallback((newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    
    // User Data should be set in localStorage by the caller (Login component) 
    // before calling login() or passed as arg.
    // For now we assume consistent localStorage state.
    const userDataStr = localStorage.getItem('user_data');
    if (userDataStr) {
      const userData = JSON.parse(userDataStr);
      setCurrentUser(parseUserFromStoredUserData(userData));
    }

    // Login clears mandant selection
    localStorage.removeItem('mandant_id');
    localStorage.removeItem('currentMandant');
    setCurrentMandant(null);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('mandant_id');
    localStorage.removeItem('currentMandant');
    localStorage.removeItem('user_data');
    localStorage.removeItem('mandanten');
    
    setToken(null);
    setCurrentUser(null);
    setCurrentMandant(null);
  }, []);

  const selectMandant = useCallback((mandant: Mandant) => {
    localStorage.setItem('mandant_id', mandant.uid);
    localStorage.setItem('currentMandant', JSON.stringify(mandant));
    setCurrentMandant(mandant);
  }, []);

  return (
    <AuthContext.Provider value={{
      token,
      currentUser,
      currentMandant,
      isAuthenticated: !!token,
      login,
      logout,
      selectMandant,
      mandantId: currentMandant?.uid || null
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
