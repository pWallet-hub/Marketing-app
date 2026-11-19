import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import {
  Badge, Empty, Field, Icon, Loading, Modal, Notice, PageHead, Pager, TYPE_LABEL, useDebounced, useLoader, useToast,
} from '../ui.jsx';

const LIMIT = 50;
const EMPTY = { email: '', name: '', organisation: '', phone: '', type: 'partner', notes: '', marketing_consent_source: '', information_consent_source: '' };
const STATUSES = ['new', 'invited', 'joined', 'unsubscribed', 'bounced', 'complained'];

export function ContactForm({ initial = EMPTY, onSubmit, submitLabel, withConsent = true, lockEmail = false, formId }) {
  const [form, setForm] = useState({ ...EMPTY, ...initial });
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  return (
    <form id={formId} className="stack" onSubmit={(e) => { e.preventDefault(); onSubmit(form); }}>
      <div className="form-grid">
        <Field label="Email"><input type="email" required value={form.email} onChange={set("email")} disabled={lockEmail} /></Field>
        <Field label="Name"><input value={form.name} onChange={set('name')} /></Field>
        <Field label="Organisation"><input value={form.organisation} onChange={set('organisation')} /></Field>
        <Field label="Phone"><input value={form.phone} onChange={set('phone')} /></Field>
        <Field label="Type">
          <select value={form.type} onChange={set('type')}>
            <option value="media">Media</option>
            <option value="partner">Partner</option>
            <option value="staff">Staff</option>
          </select>
        </Field>
        <Field label="Notes"><input value={form.notes} onChange={set('notes')} /></Field>
      </div>
      {withConsent && (
        <div className="form-grid">
          <Field label="Agreed to marketing email: where?" hint="For example: media day sign-up sheet. Leave empty if they have not agreed.">
            <input value={form.marketing_consent_source} onChange={set('marketing_consent_source')} />
          </Field>
          <Field label="Agreed to information requests: where?" hint="Leave empty if they have not agreed.">
            <input value={form.information_consent_source} onChange={set('information_consent_source')} />
          </Field>
        </div>
      )}
      {submitLabel && <div className="actions"><button className="btn btn-primary">{submitLabel}</button></div>}
    </form>
  );
}

function AddContactModal({ onClose, onDone }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  async function submit(form) {
    setError('');
    const body = { ...form };
    if (!body.marketing_consent_source) delete body.marketing_consent_source;
    if (!body.information_consent_source) delete body.information_consent_source;
    try {
      const created = await api('/contacts', { method: 'POST', body });
      toast('Contact added.');
      onDone();
      navigate(`/contacts/${created.id}`);
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <Modal title="Add a contact" wide onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="add-contact">Add contact</button></>}>
      <ContactForm formId="add-contact" onSubmit={submit} />
      <Notice kind="error">{error}</Notice>
    </Modal>
  );
}

function ImportModal({ onClose, onDone }) {
  const [csv, setCsv] = useState('');
  const [fileName, setFileName] = useState('');
  const [type, setType] = useState('media');
  const [purpose, setPurpose] = useState('');
  const [source, setSource] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const rows = csv ? Math.max(0, csv.trim().split(/\r?\n/).length - 1) : 0;

  async function onFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    setFileName(file.name);
    setCsv(await file.text());
  }

  async function submit() {
    setError('');
    setBusy(true);
    try {
      const body = { csv, type };
      if (purpose) Object.assign(body, { purpose, source });
      setResult(await api('/contacts/import', { method: 'POST', body }));
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const sample = 'data:text/csv;charset=utf-8,' + encodeURIComponent('email,name,organisation,phone,notes\njane@example.org,Jane Doe,The New Times,+250 7xx xxx xxx,Met at media day\n');
  return (
    <Modal title="Import contacts" wide onClose={onClose}
      footer={result
        ? <button className="btn btn-primary" onClick={onClose}>Done</button>
        : <><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={submit} disabled={!csv || busy || (purpose && source.trim().length < 3)}>{busy ? 'Importing…' : `Import ${rows || ''} contacts`}</button></>}>
      {result ? (
        <div className="stack">
          <Notice kind="success">Created {result.created}, updated {result.updated}. Consent recorded for {result.consent_recorded}.</Notice>
          {result.consent_skipped_suppressed > 0 && <Notice kind="warning">{result.consent_skipped_suppressed} had unsubscribed before, so their consent was not recorded.</Notice>}
          {result.errors.length > 0 && (
            <Notice kind="error">{result.errors.length} rows were skipped: {result.errors.slice(0, 8).map((e) => `line ${e.line} (${e.error})`).join(', ')}{result.errors.length > 8 ? '…' : ''}</Notice>
          )}
        </div>
      ) : (
        <div className="stack">
          <p className="muted" style={{ margin: 0 }}>
            A CSV file with a header row. <code>email</code> is required; <code>name</code>, <code>organisation</code>,
            <code>phone</code> and <code>notes</code> are optional. Existing contacts are updated, not duplicated.
            {' '}<a href={sample} download="contacts-sample.csv">Download a sample file</a>.
          </p>
          <label className="btn" style={{ alignSelf: 'flex-start' }}>
            <Icon name="upload" />{fileName || 'Choose CSV file'}
            <input type="file" accept=".csv,text/csv" onChange={onFile} className="sr-only" />
          </label>
          {csv && <p className="muted small" style={{ margin: 0 }}>{rows} rows found.</p>}
          <div className="form-grid">
            <Field label="These contacts are">
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="media">Media</option>
                <option value="partner">Partners</option>
                <option value="staff">Staff</option>
              </select>
            </Field>
            <Field label="They agreed to receive">
              <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                <option value="">Nothing yet (do not record consent)</option>
                <option value="marketing">Marketing email</option>
                <option value="information_request">Information requests</option>
              </select>
            </Field>
            {purpose && (
              <Field label="Where they agreed" hint="Required, for the record. Example: media day sign-in sheet, 12 Oct 2026.">
                <input value={source} onChange={(e) => setSource(e.target.value)} />
              </Field>
            )}
          </div>
          <Notice kind="error">{error}</Notice>
        </div>
      )}
    </Modal>
  );
}

export default function Contacts() {
  const user = useUser();
  const toast = useToast();
  const [filters, setFilters] = useState({ q: '', type: '', status: '', consent: '', list_id: '' });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState([]);
  const [listId, setListId] = useState('');
  const [modal, setModal] = useState('');
  const q = useDebounced(filters.q);

  const params = new URLSearchParams(Object.entries({ ...filters, q }).filter(([, v]) => v));
  const { data, error, loading, reload } = useLoader(
    () => api(`/contacts?${params}&limit=${LIMIT}&offset=${offset}`),
    [q, filters.type, filters.status, filters.consent, filters.list_id, offset],
  );
  const lists = useLoader(() => api('/lists'), []);
  const setFilter = (key) => (e) => { setFilters({ ...filters, [key]: e.target.value }); setOffset(0); setSelected([]); };
  const pageIds = (data?.items || []).map((c) => c.id);
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => selected.includes(id));
  const filtered = Object.values(filters).some(Boolean);

  function toggle(id) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function addToList() {
    try {
      const result = await api(`/lists/${listId}/members`, { method: 'POST', body: { contact_ids: selected } });
      toast(`Added ${result.added} to the list.`);
      setSelected([]);
      lists.reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function addAllMatching() {
    try {
      const body = { q, type: filters.type, status: filters.status, consent: filters.consent };
      const result = await api(`/lists/${listId}/members/by-filter`, { method: 'POST', body });
      toast(`Added ${result.added} matching contacts to the list.`);
      lists.reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="stack">
      <PageHead
        title="Contacts"
        subtitle="Media, partners and staff who receive your email. Consent is recorded per purpose."
        actions={(
          <>
            {user.isAdmin && <a className="btn" href={`/api/contacts/export?${params}`}><Icon name="download" />Export</a>}
            {user.isAdmin && <button className="btn" onClick={() => setModal('import')}><Icon name="upload" />Import</button>}
            <button className="btn btn-primary" onClick={() => setModal('add')}><Icon name="plus" />Add contact</button>
          </>
        )}
      />
      <section className="card card-flush">
        <div style={{ padding: '14px 18px 0' }}>
          <div className="toolbar">
            <div className="grow"><input type="search" placeholder="Search name, email or organisation" value={filters.q} onChange={setFilter('q')} /></div>
            <select value={filters.type} onChange={setFilter('type')} aria-label="Type">
              <option value="">All types</option>
              <option value="media">Media</option>
              <option value="partner">Partners</option>
              <option value="staff">Staff</option>
            </select>
            <select value={filters.consent} onChange={setFilter('consent')} aria-label="Consent">
              <option value="">Any consent</option>
              <option value="marketing">Agreed to marketing</option>
              <option value="information_request">Agreed to info requests</option>
            </select>
            <select value={filters.status} onChange={setFilter('status')} aria-label="Status">
              <option value="">Any status</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filters.list_id} onChange={setFilter('list_id')} aria-label="List">
              <option value="">In any list</option>
              {(lists.data || []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
          {(selected.length > 0 || filtered) && (
            <div className="selectbar">
              <span>{selected.length > 0 ? `${selected.length} selected` : `${data?.total ?? 0} match these filters`}</span>
              <select value={listId} onChange={(e) => setListId(e.target.value)} aria-label="List to add to">
                <option value="">Choose a list…</option>
                {(lists.data || []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
              {selected.length > 0
                ? <button className="btn btn-sm btn-primary" disabled={!listId} onClick={addToList}>Add selected to list</button>
                : <button className="btn btn-sm btn-primary" disabled={!listId} onClick={addAllMatching}>Add all {data?.total ?? ''} to list</button>}
              {selected.length > 0 && <button className="btn btn-sm btn-ghost" onClick={() => setSelected([])}>Clear selection</button>}
            </div>
          )}
        </div>
        {loading && !data && <Loading />}
        <Notice kind="error">{error}</Notice>
        {data && data.items.length === 0 && (
          <Empty icon="users" title={filtered ? 'No contacts match' : 'No contacts yet'}
            action={!filtered && <button className="btn btn-primary" onClick={() => setModal('add')}>Add a contact</button>}>
            {filtered ? 'Try different filters.' : 'Add people one by one, or import a CSV file.'}
          </Empty>
        )}
        {data && data.items.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 36 }}>
                    <input type="checkbox" aria-label="Select all on this page" checked={allOnPage}
                      onChange={() => setSelected(allOnPage ? selected.filter((id) => !pageIds.includes(id)) : [...new Set([...selected, ...pageIds])])} />
                  </th>
                  <th>Contact</th><th className="hide-sm">Organisation</th><th>Type</th><th className="hide-sm">Consent</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id}>
                    <td><input type="checkbox" aria-label={`Select ${c.email}`} checked={selected.includes(c.id)} onChange={() => toggle(c.id)} /></td>
                    <td><Link className="row-link" to={`/contacts/${c.id}`}>{c.name || c.email}</Link>{c.name && <span className="sub">{c.email}</span>}</td>
                    <td className="hide-sm">{c.organisation || <span className="faint">—</span>}</td>
                    <td>{TYPE_LABEL[c.type]}</td>
                    <td className="hide-sm">
                      <div className="btn-group" style={{ gap: 4 }}>
                        {c.marketing_consent && <Badge value="yes" label="Marketing" />}
                        {c.information_consent && <Badge value="yes" label="Info requests" />}
                        {!c.marketing_consent && !c.information_consent && <span className="faint small">None</span>}
                      </div>
                    </td>
                    <td><Badge value={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </section>
      {modal === 'add' && <AddContactModal onClose={() => setModal('')} onDone={reload} />}
      {modal === 'import' && <ImportModal onClose={() => setModal('')} onDone={reload} />}
    </div>
  );
}
