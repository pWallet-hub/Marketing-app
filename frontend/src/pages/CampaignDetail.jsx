import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import {
  Badge, Empty, Field, Icon, Loading, Modal, Notice, PageHead, Pager, PURPOSE_LABEL, Stat, Tabs,
  formatDate, pct, useConfirm, useDebounced, useLoader, useToast,
} from '../ui.jsx';

export function EmailPreview({ preview }) {
  const [device, setDevice] = useState('desktop');
  if (!preview) return <Loading label="Building preview…" />;
  return (
    <div>
      <div className="card-head">
        <h2>Preview</h2>
        <div className="device-toggle" role="group" aria-label="Preview size">
          <button className={device === 'desktop' ? 'active' : ''} onClick={() => setDevice('desktop')}><Icon name="monitor" size={14} /> Desktop</button>
          <button className={device === 'mobile' ? 'active' : ''} onClick={() => setDevice('mobile')}><Icon name="phone" size={14} /> Mobile</button>
        </div>
      </div>
      <div className="inbox-line">
        {preview.from && <span className="muted small">{preview.from}</span>}
        <strong>{preview.subject || <span className="faint">(no subject)</span>}</strong>
        <span className="muted small">{preview.preheader}</span>
      </div>
      <div className="preview-frame-wrap">
        <iframe title="Email preview" sandbox="" srcDoc={preview.html} className={`preview-frame ${device === 'mobile' ? 'mobile' : ''}`} />
      </div>
      <p className="faint small">Shown with sample values: “Example Person” at “Example Media”.</p>
    </div>
  );
}

function ScheduleModal({ onClose, onSchedule }) {
  const soon = new Date(Date.now() + 60 * 60 * 1000);
  soon.setMinutes(0, 0, 0);
  const local = new Date(soon.getTime() - soon.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const [value, setValue] = useState(local);
  return (
    <Modal
      title="Schedule campaign"
      onClose={onClose}
      footer={(
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => onSchedule(new Date(value).toISOString())} disabled={!value}>
            <Icon name="clock" />Schedule
          </button>
        </>
      )}
    >
      <Field label="Send on" hint={`Your time zone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}. Recipients are fixed when it goes out.`}>
        <input type="datetime-local" value={value} onChange={(e) => setValue(e.target.value)} />
      </Field>
    </Modal>
  );
}

function DraftView({ campaign, reload }) {
  const user = useUser();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirm, dialog] = useConfirm();
  const templates = useLoader(() => api('/templates'), []);
  const lists = useLoader(() => api('/lists'), []);
  const preview = useLoader(() => api(`/campaigns/${campaign.id}/preview`), [campaign.id, campaign.updated_at]);
  const settings = useLoader(() => api('/settings'), []);
  const [form, setForm] = useState({
    name: campaign.name, list_id: String(campaign.list_id), template_id: String(campaign.template_id),
    purpose: campaign.purpose, reply_to: campaign.reply_to || '',
  });
  const [tests, setTests] = useState(user.email || '');
  const [busy, setBusy] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const editable = campaign.status === 'draft';
  const dirty = form.name !== campaign.name || form.list_id !== String(campaign.list_id)
    || form.template_id !== String(campaign.template_id) || form.purpose !== campaign.purpose
    || form.reply_to !== (campaign.reply_to || '');
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function act(fn, success) {
    setBusy(true);
    try {
      const result = await fn();
      if (success) toast(typeof success === 'function' ? success(result) : success);
      reload();
      return result;
    } catch (err) {
      toast(err.message, 'error');
      return null;
    } finally {
      setBusy(false);
    }
  }

  const save = () => act(() => api(`/campaigns/${campaign.id}`, {
    method: 'PATCH',
    body: { ...form, list_id: Number(form.list_id), template_id: Number(form.template_id) },
  }), 'Changes saved.');

  async function sendNow() {
    const p = preview.data;
    const ok = await confirm({
      title: 'Send this campaign now?',
      message: `It goes to ${p?.eligible ?? 'everyone'} people on “${campaign.list?.name}” who agreed to ${PURPOSE_LABEL[campaign.purpose].toLowerCase()} email.${p?.will_skip ? ` ${p.will_skip} will be skipped (no consent, unsubscribed or bounced).` : ''} This cannot be undone.`,
      confirmLabel: 'Send now',
      danger: true,
    });
    if (ok) act(() => api(`/campaigns/${campaign.id}/send`, { method: 'POST' }), (r) => `Sending to ${r.queued} people. ${r.skipped} skipped.`);
  }

  async function remove() {
    if (!(await confirm({ title: 'Delete this draft?', message: 'The draft is deleted. Templates and lists are not affected.', confirmLabel: 'Delete', danger: true }))) return;
    if (await act(() => api(`/campaigns/${campaign.id}`, { method: 'DELETE' }), 'Draft deleted.')) navigate('/campaigns');
  }

  const p = preview.data;
  const checks = [
    [campaign.list?.members > 0, campaign.list ? `List “${campaign.list.name}” has ${campaign.list.members} contacts` : 'Choose a list'],
    [p && p.eligible > 0, p ? `${p.eligible} will receive it${p.will_skip ? `, ${p.will_skip} skipped for consent or bounces` : ''}` : 'Counting recipients…'],
    [Boolean(p?.subject), p?.subject ? `Subject: “${p.subject}”` : 'The template needs a subject'],
    [Boolean(p?.preheader), p?.preheader ? 'Preview text is set' : 'Add preview text to the template (recommended)'],
    [settings.data?.mail_configured, settings.data?.mail_configured ? `Sends from ${settings.data.from}` : 'Sending is not configured yet'],
  ];

  return (
    <div className="editor-layout">
      <div className="stack">
        <section className="card">
          <div className="card-head"><h2>Details</h2>{dirty && <span className="badge badge-scheduled">Unsaved</span>}</div>
          {!editable && <Notice kind="info">This campaign is scheduled. Cancel the schedule to change it.</Notice>}
          <fieldset disabled={!editable || busy} style={{ border: 0, padding: 0, margin: 0 }} className="stack">
            <Field label="Campaign name"><input value={form.name} onChange={set('name')} /></Field>
            <div className="form-grid">
              <Field label="List">
                <select value={form.list_id} onChange={set('list_id')}>
                  {(lists.data || []).map((l) => <option key={l.id} value={l.id}>{l.name} ({l.members})</option>)}
                </select>
              </Field>
              <Field label="Type">
                <select value={form.purpose} onChange={set('purpose')}>
                  <option value="marketing">Marketing</option>
                  <option value="information_request">Information request</option>
                </select>
              </Field>
            </div>
            <Field label="Template" hint={<Link to={`/templates/${form.template_id}`}>Edit this template’s content</Link>}>
              <select value={form.template_id} onChange={set('template_id')}>
                {(templates.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Reply-to address" hint="Optional. Where replies go, for example press@… Leave empty to use the sender.">
              <input type="email" value={form.reply_to} onChange={set('reply_to')} placeholder="name@afs-rwanda.org" />
            </Field>
          </fieldset>
          {editable && (
            <div className="actions">
              <button className="btn btn-primary" disabled={!dirty || busy} onClick={save}>Save changes</button>
              <button className="btn btn-ghost" disabled={busy} onClick={remove}><Icon name="trash" />Delete draft</button>
            </div>
          )}
        </section>

        <section className="card">
          <h2>Ready to send?</h2>
          <ul className="checklist">
            {checks.map(([ok, text]) => (
              <li key={text}><Icon name={ok ? 'check' : 'alert'} size={16} className={ok ? 'ok' : 'bad'} /><span>{text}</span></li>
            ))}
          </ul>
        </section>

        <section className="card">
          <h2>Send a test</h2>
          <p className="section-note">Up to five addresses, separated by commas. The subject starts with [Test].</p>
          <div className="toolbar">
            <div className="grow"><input value={tests} onChange={(e) => setTests(e.target.value)} placeholder="you@afs-rwanda.org" /></div>
            <button className="btn" disabled={busy || !tests.trim() || !user.isAdmin || dirty}
              onClick={() => act(() => api(`/campaigns/${campaign.id}/test`, { method: 'POST', body: { emails: tests.split(',').map((x) => x.trim()).filter(Boolean) } }), (r) => `Test sent to ${r.sent_to.join(', ')}.`)}>
              <Icon name="mail" />Send test
            </button>
          </div>
          {dirty && <p className="hint">Save your changes before testing.</p>}
        </section>

        <section className="card">
          <h2>{campaign.status === 'scheduled' ? 'Scheduled' : 'Send'}</h2>
          {campaign.status === 'scheduled' && (
            <Notice kind="warning">Goes out {formatDate(campaign.scheduled_for)}.</Notice>
          )}
          {!user.isAdmin ? <p className="muted">Only administrators can send or schedule. Your draft is saved for them.</p> : (
            <div className="actions">
              {campaign.status === 'scheduled' ? (
                <>
                  <button className="btn" disabled={busy} onClick={() => act(() => api(`/campaigns/${campaign.id}/unschedule`, { method: 'POST' }), 'Schedule cancelled. The campaign is a draft again.')}>Cancel schedule</button>
                  <button className="btn btn-danger" disabled={busy} onClick={sendNow}><Icon name="send" />Send now instead</button>
                </>
              ) : (
                <>
                  <button className="btn btn-primary" disabled={busy || dirty} onClick={sendNow}><Icon name="send" />Send now</button>
                  <button className="btn" disabled={busy || dirty} onClick={() => setScheduling(true)}><Icon name="clock" />Schedule…</button>
                </>
              )}
            </div>
          )}
        </section>
      </div>

      <section className="card preview-panel">
        {preview.error ? <Notice kind="error">{preview.error}</Notice> : <EmailPreview preview={p} />}
      </section>

      {scheduling && (
        <ScheduleModal
          onClose={() => setScheduling(false)}
          onSchedule={(when) => { setScheduling(false); act(() => api(`/campaigns/${campaign.id}/schedule`, { method: 'POST', body: { send_at: when } }), `Scheduled for ${formatDate(when)}.`); }}
        />
      )}
      {dialog}
    </div>
  );
}

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'opened', label: 'Opened' },
  { value: 'clicked', label: 'Clicked' },
  { value: 'not_opened', label: 'Not opened' },
  { value: 'bounced', label: 'Bounced' },
  { value: 'failed', label: 'Failed' },
  { value: 'skipped', label: 'Skipped' },
];

function ReportView({ campaign }) {
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const query = useDebounced(q);
  const report = useLoader(
    () => api(`/campaigns/${campaign.id}/report?${new URLSearchParams({ filter, q: query, offset, limit: 50 })}`),
    [campaign.id, filter, query, offset],
  );
  const preview = useLoader(() => api(`/campaigns/${campaign.id}/preview`), [campaign.id]);
  const [showEmail, setShowEmail] = useState(false);
  const s = report.data?.stats || campaign.stats;

  return (
    <div className="stack">
      {campaign.status === 'sending' && (
        <Notice kind="info">Sending now: {s.queued} still in the queue. This page updates when you reload it.</Notice>
      )}
      <div className="stats">
        <Stat label="Recipients" value={s.recipients} sub={`${s.skipped} skipped`} />
        <Stat label="Delivered" value={s.delivered} sub={`${s.sent} sent`} />
        <Stat label="Opened" value={pct(s.open_rate)} sub={`${s.opened} ${s.opened === 1 ? 'person' : 'people'}`} rate={s.open_rate} />
        <Stat label="Clicked" value={pct(s.click_rate)} sub={`${s.clicked} ${s.clicked === 1 ? 'person' : 'people'}`} rate={s.click_rate} />
        <Stat label="Bounced" value={pct(s.bounce_rate)} sub={`${s.bounced} addresses`} rate={s.bounce_rate} />
        <Stat label="Unsubscribed" value={pct(s.unsubscribe_rate)} sub={`${s.unsubscribed} ${s.unsubscribed === 1 ? 'person' : 'people'}`} rate={s.unsubscribe_rate} />
      </div>

      <div className="cols">
        <section className="card card-flush">
          <div style={{ padding: '6px 18px 0' }}>
            <Tabs tabs={FILTERS} value={filter} onChange={(v) => { setFilter(v); setOffset(0); }} />
            <div className="toolbar"><div className="grow"><input type="search" placeholder="Search recipients" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} /></div></div>
          </div>
          {report.loading && !report.data && <Loading />}
          <Notice kind="error">{report.error}</Notice>
          {report.data && report.data.items.length === 0 && <Empty icon="users" title="Nobody here">No recipients match this filter.</Empty>}
          {report.data && report.data.items.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Recipient</th><th>Status</th><th className="hide-sm">Opened</th><th className="hide-sm">Clicked</th></tr></thead>
                <tbody>
                  {report.data.items.map((r) => (
                    <tr key={r.id}>
                      <td><Link className="row-link" to={`/contacts/${r.contact_id}`}>{r.name || r.email}</Link><span className="sub">{r.email}</span></td>
                      <td><Badge value={r.status} />{(r.skip_reason || r.error) && <span className="sub">{r.skip_reason || r.error}</span>}</td>
                      <td className="hide-sm">{r.opened_at ? <>{formatDate(r.opened_at)}<span className="sub">{r.open_count}×</span></> : '—'}</td>
                      <td className="hide-sm">{r.clicked_at ? <>{formatDate(r.clicked_at)}<span className="sub">{r.click_count}×</span></> : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pager total={report.data.total} limit={50} offset={offset} onChange={setOffset} />
            </div>
          )}
        </section>

        <div className="stack">
          <section className="card">
            <h2>Top links</h2>
            {(report.data?.links || []).length === 0 ? <p className="muted small" style={{ margin: 0 }}>No clicks recorded yet. Clicks are tracked when link tracking is on for the sending domain in Resend.</p> : (
              <ul className="checklist">
                {report.data.links.map((l) => (
                  <li key={l.link}>
                    <Icon name="link" size={16} />
                    <span style={{ minWidth: 0 }}>
                      <a href={l.link} target="_blank" rel="noreferrer" style={{ overflowWrap: 'anywhere' }}>{l.link}</a>
                      <span className="sub muted small">{l.clicks} {l.clicks === 1 ? "click" : "clicks"} by {l.people} {l.people === 1 ? "person" : "people"}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="card">
            <h2>Details</h2>
            <dl className="kv">
              <dt>Sent</dt><dd>{formatDate(campaign.sent_at)}</dd>
              <dt>List</dt><dd>{campaign.list ? <Link to={`/lists/${campaign.list.id}`}>{campaign.list.name}</Link> : 'One contact (invite)'}</dd>
              <dt>Type</dt><dd>{PURPOSE_LABEL[campaign.purpose]}</dd>
              <dt>Template</dt><dd><Link to={`/templates/${campaign.template?.id}`}>{campaign.template?.name}</Link></dd>
              {campaign.reply_to && <><dt>Reply-to</dt><dd>{campaign.reply_to}</dd></>}
              <dt>Created by</dt><dd>{campaign.created_by || '—'}</dd>
            </dl>
            <div className="actions"><button className="btn" onClick={() => setShowEmail(true)}><Icon name="eye" />View email</button></div>
          </section>
        </div>
      </div>
      {showEmail && <Modal title="Email" wide onClose={() => setShowEmail(false)}><EmailPreview preview={preview.data} /></Modal>}
    </div>
  );
}

export default function CampaignDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { data, error, loading, reload } = useLoader(() => api(`/campaigns/${id}`), [id]);
  if (loading && !data) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;

  async function duplicate() {
    try {
      const copy = await api(`/campaigns/${id}/duplicate`, { method: 'POST' });
      toast('Copied as a new draft.');
      navigate(`/campaigns/${copy.id}`);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const draft = data.status === 'draft' || data.status === 'scheduled';
  return (
    <div className="stack">
      <PageHead
        crumbs={<Link to="/campaigns"><Icon name="arrowLeft" size={12} /> Campaigns</Link>}
        title={<>{data.name} <Badge value={data.status} /></>}
        subtitle={draft ? `${PURPOSE_LABEL[data.purpose]} · ${data.list?.name || ''}` : `Sent ${formatDate(data.sent_at)} to ${data.stats.recipients} people`}
        actions={(
          <>
            {!draft && <button className="btn" onClick={reload}>Refresh</button>}
            {data.list_id && <button className="btn" onClick={duplicate}><Icon name="copy" />Duplicate</button>}
          </>
        )}
      />
      {draft ? <DraftView campaign={data} reload={reload} /> : <ReportView campaign={data} />}
    </div>
  );
}
