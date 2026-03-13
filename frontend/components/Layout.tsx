
import React, { useState } from 'react';
import { NAV_ITEMS } from '../constants';
import branding from '../branding';

interface LayoutProps {
  children: React.ReactNode;
  activePath: string;
  onNavigate: (path: string) => void;
}

const Layout: React.FC<LayoutProps> = ({ children, activePath, onNavigate }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { colors } = branding;

  return (
    <div className="min-h-screen flex transition-colors duration-300">
      {/* Sidebar */}
      <aside
        style={{ backgroundColor: colors.sidebarBg, borderColor: colors.sidebarBorder }}
        className={`${sidebarOpen ? 'w-64' : 'w-20'} transition-all duration-300 flex flex-col fixed inset-y-0 z-50`}
      >
        {/* Logo / App Name */}
        <div
          style={{ borderBottomColor: colors.sidebarBorder }}
          className="h-16 flex items-center justify-between px-6 border-b"
        >
          <div className={`flex items-center gap-3 transition-opacity duration-300 ${sidebarOpen ? 'opacity-100' : 'opacity-0 overflow-hidden'}`}>
            {branding.logoUrl ? (
              <img src={branding.logoUrl} alt={branding.appName} className="w-8 h-8 rounded-lg object-cover" />
            ) : (
              <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white" style={{ backgroundColor: colors.accent }}>
                <i className={`fas ${branding.logoIcon}`}></i>
              </div>
            )}
            <div className={`transition-opacity ${sidebarOpen ? 'opacity-100' : 'opacity-0 w-0 overflow-hidden'}`}>
              <span className="font-bold text-white block leading-tight">{branding.appName}</span>
              <span className="text-[10px] block leading-tight" style={{ color: colors.accentLight }}>
                {branding.slogan.split('\n').map((line, i) => (
                  <span key={i}>{line}{i === 0 ? <br /> : null}</span>
                ))}
              </span>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ color: colors.sidebarText }}
            className="hover:text-white flex-shrink-0 transition-colors"
          >
            <i className={`fas ${sidebarOpen ? 'fa-angle-left' : 'fa-angle-right'}`}></i>
          </button>
        </div>

        {/* Nav Items */}
        <nav className="flex-1 mt-6 px-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = activePath === item.path;
            return (
              <button
                key={item.path}
                onClick={() => onNavigate(item.path)}
                style={isActive
                  ? { backgroundColor: colors.accent, color: '#ffffff', boxShadow: `0 4px 14px ${colors.accent}55` }
                  : { color: colors.sidebarText }
                }
                onMouseEnter={e => { if (!isActive) { (e.currentTarget as HTMLElement).style.backgroundColor = colors.sidebarItemHover; (e.currentTarget as HTMLElement).style.color = colors.sidebarTextHover; } }}
                onMouseLeave={e => { if (!isActive) { (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent'; (e.currentTarget as HTMLElement).style.color = colors.sidebarText; } }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-left"
              >
                <div className="w-6 text-center">{item.icon}</div>
                <span className={`font-medium transition-opacity ${sidebarOpen ? 'opacity-100' : 'opacity-0 w-0 overflow-hidden'}`}>
                  {item.label}
                </span>
              </button>
            );
          })}
        </nav>

        {/* User Profile */}
        <div className="p-4 border-t" style={{ borderTopColor: colors.sidebarBorder }}>
          <div className={`flex items-center gap-3 ${sidebarOpen ? '' : 'justify-center'}`}>
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs text-white font-medium"
              style={{ backgroundColor: colors.accentDark }}
            >
              {branding.user.initials}
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{branding.user.name}</p>
                <p className="text-xs truncate" style={{ color: colors.sidebarText }}>{branding.user.plan}</p>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main Area */}
      <main className={`flex-1 transition-all duration-300 ${sidebarOpen ? 'ml-64' : 'ml-20'}`}>
        <header className="h-16 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between px-8 sticky top-0 z-40">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">
              {NAV_ITEMS.find(n => n.path === activePath)?.label || 'Dashboard'}
            </h2>
            <p className="text-[10px] text-slate-400 leading-none mt-0.5 font-medium">{branding.tagline}</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => onNavigate('/docs')}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 hover:text-slate-800 text-xs font-medium transition-colors"
            >
              <i className="fas fa-circle-question"></i> Help & Docs
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
