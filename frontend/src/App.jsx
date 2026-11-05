import { useEffect, useState } from 'react';
import { Navigate, NavLink, Route, Routes, Outlet } from 'react-router-dom';
import { api, ApiError, signInUrl, signOutUrl } from './api.js';
import { Loading, Notice } from './ui.jsx';
import { UserContext } from './session.js';
import Dashboard from './pages/Dashboard.jsx';
import Contacts from './pages/Contacts.jsx';
import ContactDetail from './pages/ContactDetail.jsx';
import Library from './pages/Library.jsx';
import Campaigns from './pages/Campaigns.jsx';
import CampaignDetail from './pages/CampaignDetail.jsx';
import { Unsubscribe, InfoForm } from './pages/Public.jsx';


function SignIn({ message }) {
  return (
    <div className="signin">
      <h1>AFS Marketing Mailer</h1>
      <p>Sign in with your AFS account to continue.</p>
      {message && <Notice kind="error">{message}</Notice>}
      <a className="btn btn-primary" href={signInUrl}>Sign in with AFS SSO</a>
    </div>
  );
}

function Shell() {
  const [state, setState] = useState({ user: null, error: '', checked: false });

  useEffect(() => {
    api('/me')
      .then((user) => setState({ user, error: '', checked: true }))
      .catch((err) => {
        const message = err instanceof ApiError && err.status !== 401 ? err.message : '';
        setState({ user: null, error: message, checked: true });
      });
  }, []);

  if (!state.checked) return <Loading label="Checking your sign-in…" />;
  if (!state.user) return <SignIn message={state.error} />;

  const isAdmin = state.user.role === 'admin';
  return (
    <UserContext.Provider value={{ ...state.user, isAdmin }}>
      <div className="layout">
        <header className="topbar">
          <strong>AFS Marketing Mailer</strong>
          <nav>
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/contacts">Contacts</NavLink>
            <NavLink to="/library">Lists &amp; templates</NavLink>
            <NavLink to="/campaigns">Campaigns</NavLink>
          </nav>
          <div className="who">
            <span className="muted">{state.user.name || state.user.email} · {state.user.role}</span>
            <a href={signOutUrl}>Sign out</a>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </UserContext.Provider>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/unsubscribe/:token" element={<Unsubscribe />} />
      <Route path="/forms/:token" element={<InfoForm />} />
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="contacts" element={<Contacts />} />
        <Route path="contacts/:id" element={<ContactDetail />} />
        <Route path="library" element={<Library />} />
        <Route path="campaigns" element={<Campaigns />} />
        <Route path="campaigns/:id" element={<CampaignDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
