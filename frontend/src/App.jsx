import { useEffect, useState } from 'react';
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { api, ApiError, signInUrl, signOutUrl } from './api.js';
import { Icon, Loading, Notice, ToastProvider } from './ui.jsx';
import { UserContext } from './session.js';
import Dashboard from './pages/Dashboard.jsx';
import Contacts from './pages/Contacts.jsx';
import ContactDetail from './pages/ContactDetail.jsx';
import Lists from './pages/Lists.jsx';
import ListDetail from './pages/ListDetail.jsx';
import Templates from './pages/Templates.jsx';
import TemplateEditor from './pages/TemplateEditor.jsx';
import Campaigns from './pages/Campaigns.jsx';
import CampaignDetail from './pages/CampaignDetail.jsx';
import Suppressions from './pages/Suppressions.jsx';
import Activity from './pages/Activity.jsx';
import Settings from './pages/Settings.jsx';
import { InfoForm, Unsubscribe } from './pages/Public.jsx';

function SignIn({ message }) {
  return (
    <div className="signin-page">
      <div className="signin-card">
        <div className="brand-mark">AFS</div>
        <h1>Marketing Mailer</h1>
        <p className="muted">Email campaigns for Alliance for Science Rwanda. Sign in with your AFS account.</p>
        {message && <Notice kind="error">{message}</Notice>}
        <a className="btn btn-primary" href={signInUrl}>Sign in with AFS SSO</a>
      </div>
    </div>
  );
}

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/campaigns', label: 'Campaigns', icon: 'send' },
  { section: 'Audience' },
  { to: '/contacts', label: 'Contacts', icon: 'users' },
  { to: '/lists', label: 'Lists', icon: 'list' },
  { to: '/suppressions', label: 'Do not contact', icon: 'block' },
  { section: 'Content' },
  { to: '/templates', label: 'Templates', icon: 'template' },
  { section: 'Admin' },
  { to: '/activity', label: 'Activity log', icon: 'activity', admin: true },
  { to: '/settings', label: 'Settings', icon: 'settings' },
];

function Shell() {
  const [state, setState] = useState({ user: null, error: '', checked: false });
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    api('/me')
      .then((user) => setState({ user, error: '', checked: true }))
      .catch((err) => {
        const message = err instanceof ApiError && err.status !== 401 ? err.message : '';
        setState({ user: null, error: message, checked: true });
      });
  }, []);
  useEffect(() => setNavOpen(false), [location.pathname]);

  if (!state.checked) return <Loading label="Checking your sign-in…" />;
  if (!state.user) return <SignIn message={state.error} />;

  const isAdmin = state.user.role === 'admin';
  return (
    <UserContext.Provider value={{ ...state.user, isAdmin }}>
      <div className={`app ${navOpen ? 'nav-open' : ''}`}>
        <aside className="sidebar" aria-label="Main">
          <NavLink to="/" className="brand">
            <span className="brand-mark">AFS</span>
            <span className="brand-name">Marketing Mailer<small>Alliance for Science Rwanda</small></span>
          </NavLink>
          <nav className="nav">
            {NAV.filter((item) => !item.admin || isAdmin).map((item) => (
              item.section
                ? <div key={item.section} className="nav-section">{item.section}</div>
                : (
                  <NavLink key={item.to} to={item.to} end={item.end}>
                    <Icon name={item.icon} />{item.label}
                  </NavLink>
                )
            ))}
          </nav>
          <div className="sidebar-foot">
            <div className="who-name">{state.user.name || state.user.email}<span className="role-pill">{state.user.role}</span></div>
            <div className="faint small" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{state.user.email}</div>
            <a href={signOutUrl} className="small" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', marginTop: 8 }}>
              <Icon name="logout" size={14} />Sign out
            </a>
          </div>
        </aside>
        <div className="nav-scrim" onClick={() => setNavOpen(false)} />
        <div className="main">
          <div className="mobilebar">
            <button onClick={() => setNavOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
            <strong>AFS Marketing Mailer</strong>
          </div>
          <main className="content">
            <Outlet />
          </main>
        </div>
      </div>
    </UserContext.Provider>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/unsubscribe/:token" element={<Unsubscribe />} />
        <Route path="/forms/:token" element={<InfoForm />} />
        <Route element={<Shell />}>
          <Route index element={<Dashboard />} />
          <Route path="campaigns" element={<Campaigns />} />
          <Route path="campaigns/:id" element={<CampaignDetail />} />
          <Route path="contacts" element={<Contacts />} />
          <Route path="contacts/:id" element={<ContactDetail />} />
          <Route path="lists" element={<Lists />} />
          <Route path="lists/:id" element={<ListDetail />} />
          <Route path="templates" element={<Templates />} />
          <Route path="templates/:id" element={<TemplateEditor />} />
          <Route path="suppressions" element={<Suppressions />} />
          <Route path="activity" element={<Activity />} />
          <Route path="settings" element={<Settings />} />
          <Route path="library" element={<Navigate to="/templates" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ToastProvider>
  );
}
