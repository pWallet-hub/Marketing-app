import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import { Badge, Field, Loading, Notice, formatDate, useLoader } from '../ui.jsx';

const STATES = ['queued', 'sent', 'delivered', 'bounced', 'complained', 'failed', 'skipped'];

export default function CampaignDetail() {
  const { id } = useParams();
  const user = useUser();
  const { data, error, loading, reload } = useLoader(() => api(`/campaigns/${id}`), [id]);
  const [testEmail, setTestEmail] = useState('');
  const [message, setMessage] = useState({ kind: '', text: '' });
  const [busy, setBusy] = useState(false);

  async function run(action, success) {
    setBusy(true);
    setMessage({ kind: '', text: '' });
    try {
      const result = await action();
      setMessage({ kind: 'success', text: success(result) });
      reload();
    } catch (err) {
      setMessage({ kind: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  }

  function sendNow() {
    if (!window.confirm('Send this campaign to everyone on the list who has agreed to receive it? This cannot be undone.')) return;
    run(() => api(`/campaigns/${id}/send`, { method: 'POST' }), (r) => `Queued ${r.queued} emails. ${r.skipped} skipped (no consent, suppressed, or unsubscribed).`);
  }

  if (loading) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;

  return (
    <div className="stack">
      <p><Link to="/campaigns">← Campaigns</Link></p>
      <h1>{data.name}</h1>
      <section className="card">
        <dl className="details">
          <dt>Status</dt><dd><Badge value={data.status} /></dd>
          <dt>Purpose</dt><dd>{data.purpose.replace('_', ' ')}</dd>
          <dt>Sent</dt><dd>{formatDate(data.sent_at)}</dd>
        </dl>
        <div className="counts">
          {STATES.map((s) => (
            <div key={s} className="stat"><div className="stat-value">{data.counts[s] || 0}</div><div className="muted">{s}</div></div>
          ))}
        </div>
      </section>

      {data.status === 'draft' && (
        <section className="card">
          <h2>Before you send</h2>
          <p className="muted">Send a test to yourself first. Test sends have no unsubscribe link, so use them only to check the content.</p>
          <div className="actions">
            <Field label="Test address">
              <input type="email" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} />
            </Field>
            <button className="btn" disabled={busy || !testEmail || !user.isAdmin}
              onClick={() => run(() => api(`/campaigns/${id}/test`, { method: 'POST', body: { email: testEmail } }), () => 'Test sent. Check the inbox.')}>
              Send test
            </button>
          </div>
          {user.isAdmin
            ? <button className="btn btn-danger" disabled={busy} onClick={sendNow}>Send campaign</button>
            : <p className="muted">Only administrators can send a campaign.</p>}
        </section>
      )}

      <Notice kind={message.kind}>{message.text}</Notice>

      <section className="card">
        <h2>Recent recipients</h2>
        <table>
          <thead><tr><th>Email</th><th>Status</th><th>Reason or error</th><th>Sent</th></tr></thead>
          <tbody>
            {data.recent.map((r) => (
              <tr key={r.id}>
                <td>{r.email}</td>
                <td><Badge value={r.status} /></td>
                <td>{r.skip_reason || r.error || '—'}</td>
                <td>{formatDate(r.sent_at)}</td>
              </tr>
            ))}
            {data.recent.length === 0 && <tr><td colSpan="4" className="muted">Not sent yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
