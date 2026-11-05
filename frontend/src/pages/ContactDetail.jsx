import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import { Badge, Field, Loading, Notice, formatDate, useLoader } from '../ui.jsx';

export default function ContactDetail() {
  const { id } = useParams();
  const user = useUser();
  const { data: contact, error, loading, reload } = useLoader(() => api(`/contacts/${id}`), [id]);
  const templates = useLoader(() => api('/templates'), []);
  const [message, setMessage] = useState({ kind: '', text: '' });
  const [consentSource, setConsentSource] = useState('');
  const [templateId, setTemplateId] = useState('');

  async function run(action, success) {
    setMessage({ kind: '', text: '' });
    try {
      await action();
      setMessage({ kind: 'success', text: success });
      reload();
    } catch (err) {
      setMessage({ kind: 'error', text: err.message });
    }
  }

  if (loading) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;

  const activeConsent = (purpose) => contact.consents.some((c) => c.purpose === purpose && !c.withdrawn_at);
  const suppressedFor = (purpose) => contact.suppressions.some((s) => s.purpose === purpose || s.purpose === 'all');

  return (
    <div className="stack">
      <p><Link to="/contacts">← Contacts</Link></p>
      <h1>{contact.name || contact.email}</h1>
      <section className="card">
        <dl className="details">
          <dt>Email</dt><dd>{contact.email}</dd>
          <dt>Organisation</dt><dd>{contact.organisation || '—'}</dd>
          <dt>Phone</dt><dd>{contact.phone || '—'}</dd>
          <dt>Type</dt><dd>{contact.type}</dd>
          <dt>Status</dt><dd><Badge value={contact.status} /></dd>
          <dt>Blog account</dt><dd>{contact.blog_account_id || 'none'}</dd>
          <dt>Notes</dt><dd>{contact.notes || '—'}</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Consent</h2>
        {['marketing', 'information_request'].map((purpose) => (
          <div key={purpose} className="row">
            <strong>{purpose === 'marketing' ? 'Marketing email' : 'Information requests'}</strong>
            <span>{activeConsent(purpose) ? 'Agreed' : 'Not agreed'}</span>
            {suppressedFor(purpose) && <Badge value="suppressed" />}
            {user.isAdmin && activeConsent(purpose) && (
              <button className="btn" onClick={() => run(() => api(`/contacts/${id}/consent/withdraw`, { method: 'POST', body: { purpose } }), 'Consent withdrawn.')}>Withdraw</button>
            )}
          </div>
        ))}
        <div className="actions">
          <input placeholder="Where they agreed to marketing email" value={consentSource} onChange={(e) => setConsentSource(e.target.value)} />
          <button className="btn" disabled={consentSource.trim().length < 3}
            onClick={() => run(() => api(`/contacts/${id}/consent`, { method: 'POST', body: { purpose: 'marketing', source: consentSource.trim() } }), 'Consent recorded.')}>
            Record marketing consent
          </button>
        </div>
        <p className="muted">Consent is recorded with where it came from. A withdrawn consent is kept on record.</p>
      </section>

      {contact.type === 'media' && (
        <section className="card">
          <h2>Invite to join AFS</h2>
          <p className="muted">Creates this person's default blog account (when configured) and sends the invite email.</p>
          <div className="actions">
            <select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">Choose an invite template…</option>
              {(templates.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <button className="btn btn-primary" disabled={!templateId || !user.isAdmin}
              onClick={() => run(() => api(`/contacts/${id}/invite?template_id=${templateId}`, { method: 'POST' }), 'Invite queued.')}>
              Send invite
            </button>
          </div>
          {!user.isAdmin && <p className="muted">Only administrators can send invites.</p>}
        </section>
      )}

      <Notice kind={message.kind}>{message.text}</Notice>

      <section className="card">
        <h2>Lists</h2>
        {contact.lists.length === 0 ? <p className="muted">Not in any list.</p> : (
          <ul>{contact.lists.map((l) => <li key={l.id}>{l.name}</li>)}</ul>
        )}
      </section>

      <section className="card">
        <h2>Emails</h2>
        {contact.sends.length === 0 ? <p className="muted">No campaign emails yet.</p> : (
          <table>
            <thead><tr><th>Campaign</th><th>Status</th><th>Reason</th><th>Sent</th></tr></thead>
            <tbody>
              {contact.sends.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/campaigns/${s.campaign_id}`}>{s.campaign}</Link></td>
                  <td><Badge value={s.status} /></td>
                  <td>{s.skip_reason || '—'}</td>
                  <td>{formatDate(s.sent_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
