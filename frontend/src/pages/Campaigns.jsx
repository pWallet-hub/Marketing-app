import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { Badge, Field, Loading, Notice, formatDate, useLoader } from '../ui.jsx';

function NewCampaign({ templates, lists, onCreated }) {
  const [form, setForm] = useState({ name: '', template_id: '', list_id: '', purpose: 'marketing' });
  const [error, setError] = useState('');
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(event) {
    event.preventDefault();
    setError('');
    try {
      const body = { name: form.name, template_id: Number(form.template_id), list_id: Number(form.list_id), purpose: form.purpose };
      await api('/campaigns', { method: 'POST', body });
      setForm({ name: '', template_id: '', list_id: '', purpose: 'marketing' });
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <h2>New campaign</h2>
      <form className="grid" onSubmit={submit}>
        <Field label="Name"><input required value={form.name} onChange={set('name')} /></Field>
        <Field label="Template">
          <select required value={form.template_id} onChange={set('template_id')}>
            <option value="">Choose…</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="List">
          <select required value={form.list_id} onChange={set('list_id')}>
            <option value="">Choose…</option>
            {lists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.members})</option>)}
          </select>
        </Field>
        <Field label="Purpose" hint="Only people who agreed to this purpose receive it.">
          <select value={form.purpose} onChange={set('purpose')}>
            <option value="marketing">Marketing email</option>
            <option value="information_request">Information request (includes a form link)</option>
          </select>
        </Field>
        <div className="actions"><button className="btn btn-primary">Create draft</button></div>
      </form>
      <Notice kind="error">{error}</Notice>
    </section>
  );
}

export default function Campaigns() {
  const campaigns = useLoader(() => api('/campaigns'), []);
  const templates = useLoader(() => api('/templates'), []);
  const lists = useLoader(() => api('/lists'), []);
  if (campaigns.loading || templates.loading || lists.loading) return <Loading />;
  return (
    <div className="stack">
      <h1>Campaigns</h1>
      <Notice kind="error">{campaigns.error}</Notice>
      <section className="card">
        {campaigns.data && campaigns.data.length === 0 && <p className="muted">No campaigns yet.</p>}
        {campaigns.data && campaigns.data.length > 0 && (
          <table>
            <thead><tr><th>Name</th><th>Template</th><th>List</th><th>Purpose</th><th>Status</th><th>Recipients</th><th>Sent</th></tr></thead>
            <tbody>
              {campaigns.data.map((c) => (
                <tr key={c.id}>
                  <td><Link to={`/campaigns/${c.id}`}>{c.name}</Link></td>
                  <td>{c.template}</td>
                  <td>{c.list_name || 'single contact'}</td>
                  <td>{c.purpose.replace('_', ' ')}</td>
                  <td><Badge value={c.status} /></td>
                  <td>{c.recipients}</td>
                  <td>{formatDate(c.sent_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <NewCampaign templates={templates.data || []} lists={lists.data || []} onCreated={campaigns.reload} />
    </div>
  );
}
