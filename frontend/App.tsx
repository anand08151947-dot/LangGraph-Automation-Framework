
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
import ToolsView from './views/ToolsView';
import AuditLogView from './views/AuditLogView';
import { TemplateInfo } from './types';
import { ToastProvider } from './components/Toast';
import { ErrorBoundary } from './components/ErrorBoundary';

const App: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/');
  const [builderTemplate, setBuilderTemplate] = useState<TemplateInfo | null>(null);
  const [translationTemplate, setTranslationTemplate] = useState<TemplateInfo | null>(null);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '') || '/';
      setCurrentPath(hash);
    };
    window.addEventListener('hashchange', handleHashChange);
    handleHashChange();
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigate = (path: string, data?: any) => {
    if (path === '/builder' && data?.template) {
      setBuilderTemplate(data.template as TemplateInfo);
    }
    if (path === '/translation' && data?.template) {
      setTranslationTemplate(data.template as TemplateInfo);
    } else if (path === '/translation' && !data?.template) {
      setTranslationTemplate(null);
    }
    window.location.hash = path;
  };

  const renderContent = () => {
    switch (currentPath) {
      case '/': return <DashboardView onNavigate={navigate} />;
      case '/templates': return <TemplatesView onNavigate={navigate} />;
      case '/builder': return <BuilderView key={builderTemplate?.name ?? '__empty__'} initialTemplate={builderTemplate} onNavigate={navigate} />;
      case '/translation': return <TranslationView key={translationTemplate?.name ?? '__blank__'} initialTemplate={translationTemplate} onNavigate={navigate} />;
      case '/monitor': return <MonitorView />;
      case '/tools': return <ToolsView />;
      case '/audit': return <AuditLogView />;
      case '/export': return <ExportView />;
      case '/settings': return <SettingsView />;
      case '/docs': return <HelpView />;
      default: return <DashboardView onNavigate={navigate} />;
    }
  };

  return (
    <ErrorBoundary>
      <ToastProvider>
        <Layout activePath={currentPath} onNavigate={navigate}>
          {renderContent()}
        </Layout>
      </ToastProvider>
    </ErrorBoundary>
  );
};


export default App;

