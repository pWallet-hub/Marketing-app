import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { Loading, Notice, useLoader } from '../ui.jsx';

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="muted">{label}</div>
    </div>
  );
}

function sum(map) {
  return Object.values(map || {}).reduce((a, b) => a + b, 0);
}

export default function Dashboard() {
  const { data, error, loading } = useLoader(() => api('/dashboard'), []);
  if (loading) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;
  const sent = data.sends_last_30_days.sent || 0;
  const delivered = data.sends_last_30_days.delivered || 0;
  const bounced = data.sends_last_30_days.bounced || 0;
  return (
    <div className="stack">
      <h1>Dashboard</h1>
      <div className="stats">
        <Stat label="Contacts" value={sum(data.contacts_by_type)} />
        <Stat label="Media contacts" value={data.contacts_by_type.media || 0} />
        <Stat label="Partners" value={data.contacts_by_type.partner || 0} />
        <Stat label="Staff" value={data.contacts_by_type.staff || 0} />
        <Stat label="Emails queued" value={data.queued} />
        <Stat label="Sent in 30 days" value={sent + delivered} />
        <Stat label="Bounced in 30 days" value={bounced} />
        <Stat label="Suppressed addresses" value={data.suppressed_addresses} />
      </div>
      <section className="card">
        <h2>Quick links</h2>
        <p><Link to="/contacts">Add or import contacts</Link> · <Link to="/library">Build a list or write a template</Link> · <Link to="/campaigns">Start a campaign</Link></p>
      </section>
    </div>
  );
}
