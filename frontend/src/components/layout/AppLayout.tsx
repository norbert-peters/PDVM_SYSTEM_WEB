/**
 * AppLayout Component
 * Haupt-Layout-Container mit Header, Sidebar und Content
 */
import React, { useState } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { HorizontalNav } from './HorizontalNav';
import { useTheme } from '../../hooks/useTheme';

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  // Theme loading in background - don't block rendering
  try {
    useTheme();
  } catch (error) {
    console.error('Theme loading error:', error);
  }

  return (
    <div className="app-layout">
      <Header />
      
      <div className="main-container">
        <Sidebar
          collapsed={sidebarCollapsed}
          open={sidebarOpen}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          onOpenChange={setSidebarOpen}
        />
        
        <div className="main-content">
          <HorizontalNav />
          
          <div className="content-wrapper">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};
