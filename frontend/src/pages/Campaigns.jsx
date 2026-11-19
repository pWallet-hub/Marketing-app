import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import {
  Badge, Empty, Field, Icon, Loading, Modal, Notice, PageHead, PURPOSE_LABEL, Tabs, formatDate, pct, useLoader, useToast,
} from '../ui.jsx';

export function NewCampaignModal({ onClose, initial = {} }) {
  const navigate = useNavigate();
  const toast = useToast();
  const templates = useLoader(() => api('/templates'), []);
  const lists = useLoader(() => api('/lists'), []);
  const [form, setForm] = useState({ name: '', template_id: '', list_id: '', purpose: 'marketing', ...initial });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = { name: form.name, template_id: Number(form.template_id), list_id: Number(form.list_id), purpose: form.purpose };
      const created = await api('/campaigns', { method: 'POST', body });
      toast('Draft created. Review it, send a test, then send or schedule.');
      navigate(`/campaigns/${created.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const noTemplates = templates.data && templates.data.length === 0;
  const noLists = lists.data && lists.data.length === 0;
  return (
    <Modal
      title="New campaign"
      onClose={onClose}
      footer={(
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" form="new-campaign" disabled={busy || noTemplates || noLists}>Create draft</button>
        </>
      )}
    >
      {(templates.loading || lists.loading) ? <Loading /> : (
        <form id="new-campaign" className="stack" onSubmit={submit}>
          {noTemplates && <Notice kind="warning">You need a template first. <Link to="/templates">Create one</Link>.</Notice>}
          {noLists && <Notice kind="warning">You need a list first. <Link to="/lists">Create one</Link>.</Notice>}
          <Field label="Campaign name" hint="Only your team sees this.">
            <input required autoFocus value={form.name} onChange={set('name')} placeholder="e.g. November newsletter" />
          </Field>
          <Field label="Type of email">
            <div className="radio-cards">
              {[
                ['marketing', 'Marketing', 'News, events and stories. Goes to people who agreed to marketing email.'],
                ['information_request', 'Information request', 'Asks people to update their details through a personal form link.'],
              ].map(([value, title, text]) => (
                <label key={value} className={`radio-card ${form.purpose === value ? 'selected' : ''}`}>
                  <input type="radio" name="purpose" value={value} checked={form.purpose === value} onChange={set('purpose')} />
                  <span><strong>{title}</strong><span className="muted small">{text}</span></span>
                </label>
              ))}
            </div>
          </Field>
          <div className="form-grid">
            <Field label="Send to list">
              <select required value={form.list_id} onChange={set('list_id')}>
                <option value="">Choose a list…</option>
                {(lists.data || []).map((l) => <option key={l.id} value={l.id}>{l.name} ({l.members})</option>)}
              </select>
            </Field>
            <Field label="Template">
              <select required value={form.template_id} onChange={set('template_id')}>
                <option value="">Choose a template…</option>
                {(templates.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
          </div>
          <Notice kind="error">{error}</Notice>
        </form>
      )}
    </Modal>
  );
}

const TABS = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Drafts' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'sent', label: 'Sent' },
];

export default function Campaigns() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState('all');
  const [q, setQ] = useState('');
  const campaigns = useLoader(() => api('/campaigns'), []);
  const showNew = params.get('new') === '1';
  const setShowNew = (open) => setParams(open ? { new: '1' } : {});

  const all = campaigns.data || [];
  const isSent = (c) => c.status === 'sending' || c.status === 'done';
  const counts = {
    all: all.length,
    draft: all.filter((c) => c.status === 'draft').length,
    scheduled: all.filter((c) => c.status === 'scheduled').length,
    sent: all.filter(isSent).length,
  };
  const visible = all
    .filter((c) => tab === 'all' || (tab === 'sent' ? isSent(c) : c.status === tab))
    .filter((c) => !q || `${c.name} ${c.subject} ${c.list_name}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="stack">
      <PageHead
        title="Campaigns"
        subtitle="Write once, send to a list, and see who opened and clicked."
        actions={<button className="btn btn-primary" onClick={() => setShowNew(true)}><Icon name="plus" />New campaign</button>}
      />
      <section className="card card-flush">
        <div style={{ padding: '6px 18px 0' }}>
          <Tabs tabs={TABS.map((t) => ({ ...t, count: counts[t.value] }))} value={tab} onChange={setTab} />
          <div className="toolbar">
            <div className="grow"><input type="search" placeholder="Search campaigns" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          </div>
        </div>
        {campaigns.loading && <Loading />}
        <Notice kind="error">{campaigns.error}</Notice>
        {campaigns.data && visible.length === 0 && (
          <Empty icon="send" title={all.length ? 'No campaigns match' : 'No campaigns yet'}
            action={!all.length && <button className="btn btn-primary" onClick={() => setShowNew(true)}>Create a campaign</button>}>
            {all.length ? 'Try another tab or search.' : 'Pick a list and a template, send yourself a test, then send or schedule it.'}
          </Empty>
        )}
        {visible.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Campaign</th><th>Status</th><th className="hide-sm">Audience</th><th className="right">Recipients</th><th className="right">Opens</th><th className="right">Clicks</th></tr>
              </thead>
              <tbody>
                {visible.map((c) => {
                  const base = c.delivered || c.recipients;
                  const when = c.status === 'scheduled' ? `Scheduled for ${formatDate(c.scheduled_for)}`
                    : c.sent_at ? `Sent ${formatDate(c.sent_at)}` : `Edited ${formatDate(c.updated_at)}`;
                  return (
                    <tr key={c.id}>
                      <td>
                        <Link className="row-link" to={`/campaigns/${c.id}`}>{c.name}</Link>
                        <span className="sub">{c.subject}</span>
                        <span className="sub">{when}</span>
                      </td>
                      <td><Badge value={c.status} /></td>
                      <td className="hide-sm">{c.list_name || 'One contact (invite)'}<span className="sub">{PURPOSE_LABEL[c.purpose]}</span></td>
                      <td className="right">{isSent(c) ? c.recipients : <span className="faint">{c.list_size ?? '—'}</span>}</td>
                      <td className="right">{isSent(c) ? pct(base ? (100 * c.opened) / base : 0) : '—'}</td>
                      <td className="right">{isSent(c) ? pct(base ? (100 * c.clicked) / base : 0) : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {showNew && <NewCampaignModal onClose={() => setShowNew(false)} />}
    </div>
  );
}
