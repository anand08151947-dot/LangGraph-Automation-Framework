
import React, { useState, useEffect } from 'react';
import Layout from './components/Layout';
import DashboardView from './views/DashboardView';
import TemplatesView from './views/TemplatesView';
import BuilderView from './views/BuilderView';
import TranslationView from './views/TranslationView';
import MonitorView from './views/MonitorView';
import ExportView from './views/ExportView';
import SettingsView from './views/SettingsView';
import HelpView from './views/HelpView';

const App: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/');

  // Simple hash routing handling
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '') || '/';
      setCurrentPath(hash);
    };

    window.addEventListener('hashchange', handleHashChange);
    handleHashChange(); // Initial check

    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigate = (path: string) => {
    window.location.hash = path;
  };

  const renderContent = () => {
    switch (currentPath) {
      case '/': return <DashboardView onNavigate={navigate} />;
      case '/templates': return <TemplatesView />;
      case '/builder': return <BuilderView />;
      case '/translation': return <TranslationView />;
      case '/monitor': return <MonitorView />;
      case '/export': return <ExportView />;
      case '/settings': return <SettingsView />;
      case '/docs': return <HelpView />;
      default: return <DashboardView onNavigate={navigate} />;
    }
  };

  return (
    <Layout activePath={currentPath} onNavigate={navigate}>
      {renderContent()}
    </Layout>
  );
};

export default App;
