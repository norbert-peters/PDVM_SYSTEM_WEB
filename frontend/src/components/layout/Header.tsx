/**
 * Header Component
 * Top-Level Header mit Logo, Stichtagsbar, User-Menu und Theme-Toggle
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';

export const Header: React.FC = () => {
  const { currentUser, currentMandant } = useAuth();
  const { themeName, toggleTheme } = useTheme();
  const navigate = useNavigate();

  const getUserDisplayName = () => {
    const full = `${currentUser?.vorname || ''} ${currentUser?.nachname || ''}`.trim();
    return full || currentUser?.name || currentUser?.benutzer || currentUser?.username || 'User';
  };

  const getUserModeName = () => currentUser?.modeName || '—';

  const getMandantAddressLine = () => {
    const town = currentMandant?.town?.trim();
    const street = currentMandant?.street?.trim();
    if (town && street) return `${town} / ${street}`;
    return town || street || '';
  };

  const getUserInitials = (name?: string) => {
    if (!name) return 'U';
    return name
      .split(' ')
      .map(n => n[0])
      .filter(Boolean)
      .join('')
      .toUpperCase()
      .slice(0, 2) || 'U';
  };

  return (
    <header className="app-header">
      {/* Left: Logo & Branding */}
      <div className="header-left">
        <div className="header-logo">
        <img 
          src={'/logo.svg'} 
          alt="Logo"
          onError={(e) => {
            // Fallback wenn Bild nicht gefunden
            e.currentTarget.style.display = 'none';
          }}
        />
        <span className="header-app-title">PDVM System</span>
        </div>
      </div>

      {/* Center: Mandant Info */}
      <div className="header-center">
        {currentMandant && (
          <div className="header-mandant">
            <div className="header-mandant-name">{currentMandant.name}</div>
            {getMandantAddressLine() && (
              <div className="header-mandant-address">{getMandantAddressLine()}</div>
            )}
          </div>
        )}
      </div>

      {/* Right: Actions + User */}
      <div className="header-right">
        {/* Design anpassen */}
        <button
          className="theme-toggle"
          onClick={() => navigate('/design')}
          title="Design anpassen"
          aria-label="Design anpassen"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
          </svg>
        </button>

        {/* Theme Toggle */}
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          title={`Wechseln zu ${themeName === 'light' ? 'Dunkel' : 'Hell'}`}
          aria-label="Theme umschalten"
        >
          {themeName === 'light' ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          )}
        </button>

        {/* User */}
        {currentUser && (
          <div className="header-user-menu">
            <div className="user-info">
              <div className="user-avatar">{getUserInitials(getUserDisplayName())}</div>
              <div className="user-details">
                <div className="user-name">{getUserDisplayName()}</div>
                <div className="user-role">{getUserModeName()}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </header>
  );
};
