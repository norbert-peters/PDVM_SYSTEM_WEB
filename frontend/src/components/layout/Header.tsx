/**
 * Header Component
 * Top-Level Header mit Logo, Stichtagsbar, User-Menu und Theme-Toggle
 */
import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';

export const Header: React.FC = () => {
  const { currentUser, currentMandant } = useAuth();
  const { currentTheme, themeName, toggleTheme } = useTheme();

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
      {/* Logo & Branding */}
      <div className="header-logo">
        <img 
          src={currentTheme?.assets?.logo?.[themeName] || '/logo.svg'} 
          alt="Logo"
          onError={(e) => {
            // Fallback wenn Bild nicht gefunden
            e.currentTarget.style.display = 'none';
          }}
        />
        <span className="header-app-title">PDVM System</span>
      </div>

      {/* Stichtagsbar */}
      <div className="stichtags-bar">
        <span className="stichtags-bar-label">Stichtag:</span>
        <span className="stichtags-bar-date">
          {new Date().toLocaleDateString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
          })}
        </span>
      </div>

      {/* Spacer */}
      <div className="header-spacer" />

      {/* Mandant Info */}
      {currentMandant && (
        <div className="text-sm text-secondary">
          {currentMandant.name}
        </div>
      )}

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

      {/* User Menu */}
      {currentUser && (
        <div className="header-user-menu">
          <div className="user-info">
            <div className="user-avatar">
              {getUserInitials(currentUser.name || currentUser.benutzer || currentUser.username || 'User')}
            </div>
            <div className="user-details">
              <div className="user-name">{currentUser.name || currentUser.benutzer || currentUser.username || 'User'}</div>
              <div className="user-role">Administrator</div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
