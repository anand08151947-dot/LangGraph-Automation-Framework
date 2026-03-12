/**
 * branding.ts — Single source of truth for all app branding.
 * Edit this file to change the app name, slogan, colors, logo, and user info.
 */

const branding = {
  // App identity
  appName: 'Agentic Workbench',
  appFullName: 'Agentic AI Workbench',
  slogan: 'Orchestrate Intelligence, Automate Everything',
  version: '1.0.0',

  // Logo — set logoUrl to an image path (e.g. '/logo.svg') or leave empty to use the icon
  logoIcon: 'fa-brain',     // Font Awesome icon class (used when logoUrl is empty)
  logoUrl: '/logo.svg',     // File in frontend/public/ — takes priority over logoIcon

  // Colors — plain hex values for reliable dynamic theming (no Tailwind class dependency)
  colors: {
    sidebarBg: '#0a0f1e',         // Sidebar background
    sidebarBorder: '#1e2a3a',     // Sidebar border / divider
    sidebarText: '#94a3b8',       // Nav item text (inactive)
    sidebarTextHover: '#ffffff',  // Nav item text (hover/active)
    sidebarItemHover: '#1e2a3a',  // Nav item hover background
    accent: '#0288d1',            // Primary accent — active nav, hero, buttons
    accentDark: '#0149a3',        // Darker accent — gradients, deeper tones
    accentLight: '#81d4fa',       // Light accent — highlights
    heroText: '#e0f4ff',          // Hero subtitle text color
  },

  // User profile shown in sidebar footer
  user: {
    name: 'John Doe',
    initials: 'JD',
    plan: 'Pro Plan',
  },

  // Page title shown in browser tab
  pageTitle: 'Agentic AI Workbench',

  // Dashboard hero
  heroWelcome: (name: string) => `Welcome back, ${name}!`,
  heroSubtitle: 'Ready to deploy your next intelligent agent? Use the visual builder or let AI generate your JSON workflow config.',

  // Footer text
  footer: '✦ Agentic Workbench · Orchestrate Intelligence, Automate Everything',
};

export default branding;
