import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import { BarChart, Badge, Empty, Icon, Loading, Notice, PageHead, Stat, formatDate, pct, useLoader } from '../ui.jsx';

function total(map) {
  return Object.values(map || {}).reduce((a, b) => a + b, 0);
}

export default function Dashboard() {
  const user = useUser();
  const { data, error, loading } = useLoader(() => api('/dashboard'), []);
  const settings = useLoader(() => api('/settings'), []);
  if (loading) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;

  const e = data.engagement_30_days;
  const contacts = total(data.contacts_by_type);
  const first = (user.name || '').split(' ')[0];

  return (
    <div className="stack">
      <PageHead
        title={first ? `Welcome back, ${first}` : 'Dashboard'}
        subtitle="How your email has performed over the last 30 days."
        actions={<Link className="btn btn-primary" to="/campaigns?new=1"><Icon name="plus" />New campaign</Link>}
      />

      {settings.data && !settings.data.mail_configured && (
        <Notice kind="warning">
          Sending is not set up yet: campaigns can be prepared, but nothing is sent until the Resend key and sender
          address are configured. <Link to="/settings">See settings</Link>.
        </Notice>
      )}

      <div className="stats">
        <Stat label="Emails sent" value={e.sent} sub="last 30 days" />
        <Stat label="Open rate" value={pct(e.open_rate)} sub={`${e.opened} ${e.opened === 1 ? 'person' : 'people'} opened`} rate={e.open_rate} />
        <Stat label="Click rate" value={pct(e.click_rate)} sub={`${e.clicked} ${e.clicked === 1 ? 'person' : 'people'} clicked`} rate={e.click_rate} />
        <Stat label="Bounce rate" value={pct(e.bounce_rate)} sub={`${e.bounced} bounced`} rate={e.bounce_rate} />
      </div>

      <div className="cols">
        <section className="card">
          <div className="card-head"><h2>Sends and opens per day</h2></div>
          <BarChart data={data.daily} a="sent" b="opened" labelA="Sent" labelB="Opened" />
        </section>
        <section className="card">
          <div className="card-head"><h2>Audience</h2><Link to="/contacts" className="small">View all</Link></div>
          <dl className="kv">
            <dt>Contacts</dt><dd><strong>{contacts}</strong> <span className="faint small">(+{data.new_contacts_30_days} in 30 days)</span></dd>
            <dt>Media</dt><dd>{data.contacts_by_type.media || 0}</dd>
            <dt>Partners</dt><dd>{data.contacts_by_type.partner || 0}</dd>
            <dt>Staff</dt><dd>{data.contacts_by_type.staff || 0}</dd>
            <dt>Agreed to marketing</dt><dd>{data.consent.marketing || 0}</dd>
            <dt>Agreed to info requests</dt><dd>{data.consent.information_request || 0}</dd>
            <dt>Do not contact</dt><dd>{data.suppressed_addresses}</dd>
            <dt>In the send queue</dt><dd>{data.queued}</dd>
          </dl>
        </section>
      </div>

      <div className="cols">
        <section className="card card-flush">
          <div className="card-head"><h2>Recent campaigns</h2><Link to="/campaigns" className="small">All campaigns</Link></div>
          {data.recent_campaigns.length === 0 ? (
            <Empty icon="send" title="No campaigns sent yet" action={<Link className="btn" to="/campaigns?new=1">Create your first campaign</Link>}>
              Results appear here once a campaign goes out.
            </Empty>
          ) : (
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table>
                <thead><tr><th>Campaign</th><th className="right">Recipients</th><th className="right">Opened</th><th className="right">Clicked</th></tr></thead>
                <tbody>
                  {data.recent_campaigns.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link className="row-link" to={`/campaigns/${c.id}`}>{c.name}</Link>
                        <span className="sub">{formatDate(c.sent_at)} · <Badge value={c.status} /></span>
                      </td>
                      <td className="right">{c.stats.recipients}</td>
                      <td className="right">{pct(c.stats.open_rate)}</td>
                      <td className="right">{pct(c.stats.click_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="card">
          <div className="card-head"><h2>Scheduled</h2></div>
          {data.upcoming.length === 0 ? <p className="muted" style={{ margin: 0 }}>Nothing scheduled.</p> : (
            <ul className="checklist">
              {data.upcoming.map((c) => (
                <li key={c.id}>
                  <Icon name="clock" size={16} />
                  <span><Link to={`/campaigns/${c.id}`}>{c.name}</Link><br /><span className="muted small">{formatDate(c.scheduled_for)}</span></span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
