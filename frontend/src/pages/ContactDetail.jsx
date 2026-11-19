import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import {
  Badge, Field, Icon, Loading, Modal, Notice, PageHead, PURPOSE_LABEL, TYPE_LABEL, formatDate, useConfirm, useLoader, useToast,
} from '../ui.jsx';
import { ContactForm } from './Contacts.jsx';

const EVENT_LABEL = { delivered: 'Delivered', opened: 'Opened', clicked: 'Clicked', bounced: 'Bounced' };

export default function ContactDetail() {
  const { id } = useParams();
  const user = useUser();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirm, dialog] = useConfirm();
  const { data: contact, error, loading, reload } = useLoader(() => api(`/contacts/${id}`), [id]);
  const templates = useLoader(() => api('/templates'), []);
  const lists = useLoader(() => api('/lists'), []);
  const [modal, setModal] = useState(null);
  const [consent, setConsent] = useState({ purpose: 'marketing', source: '' });
  const [templateId, setTemplateId] = useState('');
  const [listId, setListId] = useState('');
  const [keepSuppressed, setKeepSuppressed] = useState(true);

  async function run(action, success) {
    try {
      const result = await action();
      toast(typeof success === 'function' ? success(result) : success);
      reload();
      return result;
    } catch (err) {
      toast(err.message, 'error');
      return null;
    }
  }

  if (loading && !contact) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;

  const active = (purpose) => contact.consents.find((c) => c.purpose === purpose && !c.withdrawn_at);
  const suppressedFor = (purpose) => contact.suppressions.some((s) => s.purpose === purpose || s.purpose === 'all');

  async function save(form) {
    const { name, organisation, phone, type, notes } = form;
    const ok = await run(() => api(`/contacts/${id}`, { method: 'PATCH', body: { name, organisation, phone, type, notes } }), 'Contact updated.');
    if (ok) setModal(null);
  }

  async function erase() {
    const label = contact.name || contact.email;
    if (!(await confirm({ title: `Delete ${label}?`, message: 'Everything held about them is deleted: consent records, list memberships, emails sent and form answers. This cannot be undone.', confirmLabel: 'Delete permanently', danger: true }))) return;
    try {
      const result = await api(`/contacts/${id}/erase`, { method: 'POST', body: { suppress: keepSuppressed } });
      toast(result.blog_account_id
        ? `${label} was deleted. Their Biocap blog account (${result.blog_account_id}) still exists; remove it in Biocap if needed.`
        : `${label} was deleted.`);
      navigate('/contacts');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="stack">
      <PageHead
        crumbs={<Link to="/contacts"><Icon name="arrowLeft" size={12} /> Contacts</Link>}
        title={<>{contact.name || contact.email} <Badge value={contact.status} /></>}
        subtitle={`${TYPE_LABEL[contact.type]}${contact.organisation ? ` · ${contact.organisation}` : ''} · added ${formatDate(contact.created_at)}`}
        actions={<button className="btn" onClick={() => setModal('edit')}><Icon name="edit" />Edit</button>}
      />

      <div className="cols">
        <div className="stack">
          <section className="card">
            <h2>Details</h2>
            <dl className="kv">
              <dt>Email</dt><dd><a href={`mailto:${contact.email}`}>{contact.email}</a></dd>
              <dt>Organisation</dt><dd>{contact.organisation || '—'}</dd>
              <dt>Phone</dt><dd>{contact.phone || '—'}</dd>
              <dt>Type</dt><dd>{TYPE_LABEL[contact.type]}</dd>
              <dt>Blog account</dt><dd>{contact.blog_account_id || 'None'}</dd>
              <dt>Notes</dt><dd>{contact.notes || '—'}</dd>
              <dt>Added by</dt><dd>{contact.created_by || '—'}</dd>
            </dl>
          </section>

          <section className="card card-flush">
            <div className="card-head"><h2>Activity</h2></div>
            {contact.activity.length === 0 && contact.sends.length === 0 ? <p className="muted" style={{ padding: '0 18px 12px' }}>No emails sent yet.</p> : (
              <div className="table-wrap" style={{ marginTop: 10 }}>
                <table>
                  <thead><tr><th>Campaign</th><th>Status</th><th className="hide-sm">Opened</th><th className="hide-sm">Clicked</th></tr></thead>
                  <tbody>
                    {contact.sends.map((s) => (
                      <tr key={s.id}>
                        <td><Link className="row-link" to={`/campaigns/${s.campaign_id}`}>{s.campaign}</Link><span className="sub">{formatDate(s.sent_at)}</span></td>
                        <td><Badge value={s.status} />{s.skip_reason && <span className="sub">{s.skip_reason}</span>}</td>
                        <td className="hide-sm">{formatDate(s.opened_at)}</td>
                        <td className="hide-sm">{formatDate(s.clicked_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {contact.activity.length > 0 && (
              <div style={{ padding: '4px 18px 16px' }}>
                <h3>Timeline</h3>
                <ul className="checklist">
                  {contact.activity.slice(0, 15).map((a, i) => (
                    <li key={i}>
                      <Icon name={a.type === 'clicked' ? 'link' : a.type === 'opened' ? 'eye' : a.type === 'bounced' ? 'alert' : 'mail'} size={15} />
                      <span>
                        <strong>{EVENT_LABEL[a.type] || a.type}</strong> “{a.campaign}”
                        {a.link && <> · <a href={a.link} target="_blank" rel="noreferrer">{a.link}</a></>}
                        <span className="sub muted small">{formatDate(a.at)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <h2>Consent</h2>
            {['marketing', 'information_request'].map((purpose) => {
              const c = active(purpose);
              return (
                <div key={purpose} style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                  <div className="btn-group" style={{ justifyContent: 'space-between', width: '100%' }}>
                    <strong>{PURPOSE_LABEL[purpose]}</strong>
                    {suppressedFor(purpose) ? <Badge value="suppressed" label="Do not contact" /> : c ? <Badge value="yes" label="Agreed" /> : <Badge value="no" label="Not agreed" />}
                  </div>
                  {c && <div className="muted small">{c.source} · {formatDate(c.given_at)}</div>}
                  {user.isAdmin && c && (
                    <button className="link-btn small" onClick={() => run(() => api(`/contacts/${id}/consent/withdraw`, { method: 'POST', body: { purpose } }), 'Consent withdrawn.')}>Withdraw</button>
                  )}
                </div>
              );
            })}
            <form className="stack" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); run(() => api(`/contacts/${id}/consent`, { method: 'POST', body: { purpose: consent.purpose, source: consent.source.trim() } }), 'Consent recorded.').then((r) => r && setConsent({ ...consent, source: '' })); }}>
              <Field label="Record consent">
                <select value={consent.purpose} onChange={(e) => setConsent({ ...consent, purpose: e.target.value })}>
                  <option value="marketing">Marketing email</option>
                  <option value="information_request">Information requests</option>
                </select>
              </Field>
              <input placeholder="Where they agreed, e.g. signed form 3 Nov" value={consent.source} onChange={(e) => setConsent({ ...consent, source: e.target.value })} />
              <button className="btn" disabled={consent.source.trim().length < 3}>Record consent</button>
            </form>
            {contact.consents.some((c) => c.withdrawn_at) && (
              <p className="faint small">Withdrawn consent is kept on record.</p>
            )}
          </section>

          <section className="card">
            <h2>Lists</h2>
            {contact.lists.length === 0 ? <p className="muted small">Not in any list.</p> : (
              <div className="btn-group" style={{ marginBottom: 10 }}>
                {contact.lists.map((l) => (
                  <span key={l.id} className="badge badge-draft">
                    <Link to={`/lists/${l.id}`}>{l.name}</Link>
                    <button className="link-btn" aria-label={`Remove from ${l.name}`} onClick={() => run(() => api(`/lists/${l.id}/members/${id}`, { method: 'DELETE' }), `Removed from ${l.name}.`)}>×</button>
                  </span>
                ))}
              </div>
            )}
            <div className="toolbar" style={{ marginBottom: 0 }}>
              <select value={listId} onChange={(e) => setListId(e.target.value)} aria-label="Add to list" style={{ flex: 1 }}>
                <option value="">Add to a list…</option>
                {(lists.data || []).filter((l) => !contact.lists.some((x) => x.id === l.id)).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
              <button className="btn" disabled={!listId} onClick={() => run(() => api(`/lists/${listId}/members`, { method: 'POST', body: { contact_ids: [Number(id)] } }), 'Added to list.').then(() => setListId(''))}>Add</button>
            </div>
          </section>

          {contact.type === 'media' && (
            <section className="card">
              <h2>Invite to join AFS</h2>
              <p className="section-note">Creates their blog account (when Biocap is connected) and sends the invite email. Needs marketing consent.</p>
              <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} aria-label="Invite template">
                <option value="">Choose an invite template…</option>
                {(templates.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <div className="actions">
                <button className="btn btn-primary" disabled={!templateId || !user.isAdmin}
                  onClick={() => run(() => api(`/contacts/${id}/invite?template_id=${templateId}`, { method: 'POST' }), (r) => (r.queued ? 'Invite queued.' : 'The invite could not be queued for this contact.'))}>
                  <Icon name="send" />Send invite
                </button>
              </div>
              {!user.isAdmin && <p className="muted small">Only administrators can send invites.</p>}
            </section>
          )}

          {user.isAdmin && (
            <section className="card">
              <h2>Delete contact</h2>
              <p className="section-note">For a data-protection request. Removes everything held about this person.</p>
              <label className="check small">
                <input type="checkbox" checked={keepSuppressed} onChange={(e) => setKeepSuppressed(e.target.checked)} />
                <span>Keep the address on the do-not-contact list, so a later import cannot add them back</span>
              </label>
              <div className="actions"><button className="btn btn-danger" onClick={erase}><Icon name="trash" />Delete contact</button></div>
            </section>
          )}
        </div>
      </div>

      {modal === 'edit' && (
        <Modal title="Edit contact" wide onClose={() => setModal(null)}
          footer={<><button className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn btn-primary" form="edit-contact">Save</button></>}>
          <ContactForm formId="edit-contact" initial={contact} withConsent={false} lockEmail onSubmit={save} />
        </Modal>
      )}
      {dialog}
    </div>
  );
}
