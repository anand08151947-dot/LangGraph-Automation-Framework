
import React, { useState } from 'react';
import { NAV_ITEMS } from '../constants';

interface LayoutProps {
  children: React.ReactNode;
  activePath: string;
  onNavigate: (path: string) => void;
}

const Layout: React.FC<LayoutProps> = ({ children, activePath, onNavigate }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="min-h-screen flex transition-colors duration-300">
      {/* Sidebar */}
      <aside className={`${sidebarOpen ? 'w-64' : 'w-20'} bg-slate-900 text-slate-300 transition-all duration-300 flex flex-col fixed inset-y-0 z-50`}>
        <div className="h-16 flex items-center justify-between px-6 border-b border-slate-800">
          <div className={`flex items-center gap-3 transition-opacity duration-300 ${sidebarOpen ? 'opacity-100' : 'opacity-0 overflow-hidden'}`}>
            <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center text-white">
              <i className="fas fa-brain"></i>
            </div>
            <span className="font-bold text-white whitespace-nowrap">Agentic Workbench</span>
          </div>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-slate-400 hover:text-white">
            <i className={`fas ${sidebarOpen ? 'fa-angle-left' : 'fa-angle-right'}`}></i>
          </button>
        </div>

        <nav className="flex-1 mt-6 px-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.path}
              onClick={() => onNavigate(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                activePath === item.path 
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20' 
                : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              <div className="w-6 text-center">{item.icon}</div>
              <span className={`font-medium transition-opacity ${sidebarOpen ? 'opacity-100' : 'opacity-0 w-0 overflow-hidden'}`}>
                {item.label}
              </span>
            </button>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800">
          <div className={`flex items-center gap-3 ${sidebarOpen ? '' : 'justify-center'}`}>
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs">JD</div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">John Doe</p>
                <p className="text-xs text-slate-500 truncate">Pro Plan</p>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main Area */}
      <main className={`flex-1 transition-all duration-300 ${sidebarOpen ? 'ml-64' : 'ml-20'}`}>
        <header className="h-16 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between px-8 sticky top-0 z-40">
          <h2 className="text-lg font-semibold text-slate-800">
            {NAV_ITEMS.find(n => n.path === activePath)?.label || 'Dashboard'}
          </h2>
          <div className="flex items-center gap-4">
            <button className="text-slate-500 hover:text-slate-800 relative p-2">
              <i className="fas fa-bell"></i>
              <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full"></span>
            </button>
            <button className="text-slate-500 hover:text-slate-800 p-2">
              <i className="fas fa-search"></i>
            </button>
            <div className="h-8 w-[1px] bg-slate-200 mx-2"></div>
            <button className="text-sm font-medium text-slate-600 hover:text-indigo-600">
              Support
            </button>
          </div>
        </header>

        <div className="p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;
