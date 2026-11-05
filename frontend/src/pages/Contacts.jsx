import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import { Badge, Field, Loading, Notice, Pager, useLoader } from '../ui.jsx';

const LIMIT = 50;
const EMPTY = { email: '', name: '', organisation: '', phone: '', type: 'partner', notes: '', marketing_consent_source: '', information_consent_source: '' };

function NewContact({ onCreated }) {
  const [form, setForm] = useState(EMPTY);
  const [message, setMessage] = useState({ kind: '', text: '' });
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(event) {
    event.preventDefault();
    setMessage({ kind: '', text: '' });
    try {
      const body = { ...form };
      if (!body.marketing_consent_source) delete body.marketing_consent_source;
      if (!body.information_consent_source) delete body.information_consent_source;
      await api('/contacts', { method: 'POST', body });
      setForm(EMPTY);
      setMessage({ kind: 'success', text: 'Contact added.' });
      onCreated();
    } catch (err) {
      setMessage({ kind: 'error', text: err.message });
    }
  }

  return (
    <section className="card">
      <h2>Add a contact</h2>
      <form className="grid" onSubmit={submit}>
        <Field label="Email"><input type="email" required value={form.email} onChange={set('email')} /></Field>
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
        <Field label="Marketing consent: where they agreed" hint="Leave blank if they have not agreed to marketing email.">
          <input value={form.marketing_consent_source} onChange={set('marketing_consent_source')} />
        </Field>
        <Field label="Information requests: where they agreed" hint="Leave blank if they have not agreed to information requests.">
          <input value={form.information_consent_source} onChange={set('information_consent_source')} />
        </Field>
        <div className="actions"><button className="btn btn-primary">Add contact</button></div>
      </form>
      <Notice kind={message.kind}>{message.text}</Notice>
    </section>
  );
}

function ImportContacts({ onImported }) {
  const [csv, setCsv] = useState('');
  const [type, setType] = useState('media');
  const [purpose, setPurpose] = useState('');
  const [source, setSource] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  async function onFile(event) {
    const file = event.target.files[0];
    if (file) setCsv(await file.text());
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    setResult(null);
    try {
      const body = { csv, type };
      if (purpose) Object.assign(body, { purpose, source });
      setResult(await api('/contacts/import', { method: 'POST', body }));
      onImported();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <h2>Import from CSV</h2>
      <p className="muted">The file needs a header row with <code>email</code>. Optional columns: name, organisation, phone, notes.</p>
      <form className="stack" onSubmit={submit}>
        <input type="file" accept=".csv,text/csv" onChange={onFile} />
        <div className="grid">
          <Field label="Type">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="media">Media</option>
              <option value="partner">Partner</option>
              <option value="staff">Staff</option>
            </select>
          </Field>
          <Field label="Record consent for">
            <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              <option value="">Do not record consent</option>
              <option value="marketing">Marketing email</option>
              <option value="information_request">Information requests</option>
            </select>
          </Field>
          {purpose && (
            <Field label="Where they agreed" hint="Required. For example: media day sign-in sheet, 12 Oct 2026.">
              <input value={source} onChange={(e) => setSource(e.target.value)} required />
            </Field>
          )}
        </div>
        <div className="actions"><button className="btn" disabled={!csv}>Import</button></div>
      </form>
      <Notice kind="error">{error}</Notice>
      {result && (
        <Notice kind="success">
          Created {result.created}, updated {result.updated}. Consent recorded for {result.consent_recorded}
          {result.consent_skipped_suppressed ? `, skipped ${result.consent_skipped_suppressed} who unsubscribed` : ''}.
          {result.errors.length > 0 && ` ${result.errors.length} rows had errors: ${result.errors.slice(0, 5).map((e) => `line ${e.line} (${e.error})`).join(', ')}.`}
        </Notice>
      )}
    </section>
  );
}

export default function Contacts() {
  const user = useUser();
  const [q, setQ] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState([]);
  const [listId, setListId] = useState('');
  const [note, setNote] = useState('');

  const query = new URLSearchParams({ q, type, status, limit: LIMIT, offset });
  const { data, error, loading, reload } = useLoader(() => api(`/contacts?${query}`), [q, type, status, offset]);
  const lists = useLoader(() => api('/lists'), []);

  function toggle(id) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function addToList() {
    setNote('');
    try {
      const result = await api(`/lists/${listId}/members`, { method: 'POST', body: { contact_ids: selected } });
      setNote(`Added ${result.added} to the list.`);
      setSelected([]);
      lists.reload();
    } catch (err) {
      setNote(err.message);
    }
  }

  return (
    <div className="stack">
      <h1>Contacts</h1>
      <section className="card">
        <div className="filters">
          <input placeholder="Search name, email or organisation" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
          <select value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }}>
            <option value="">All types</option>
            <option value="media">Media</option>
            <option value="partner">Partner</option>
            <option value="staff">Staff</option>
          </select>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">Any status</option>
            {['new', 'invited', 'joined', 'unsubscribed', 'bounced', 'complained'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {loading && <Loading />}
        <Notice kind="error">{error}</Notice>
        {data && (
          <>
            <table>
              <thead>
                <tr>
                  <th></th><th>Name</th><th>Email</th><th>Organisation</th><th>Type</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id}>
                    <td><input type="checkbox" aria-label={`Select ${c.email}`} checked={selected.includes(c.id)} onChange={() => toggle(c.id)} /></td>
                    <td><Link to={`/contacts/${c.id}`}>{c.name || '(no name)'}</Link></td>
                    <td>{c.email}</td>
                    <td>{c.organisation}</td>
                    <td>{c.type}</td>
                    <td><Badge value={c.status} /></td>
                  </tr>
                ))}
                {data.items.length === 0 && <tr><td colSpan="6" className="muted">No contacts match.</td></tr>}
              </tbody>
            </table>
            <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
        {selected.length > 0 && (
          <div className="actions">
            <span>{selected.length} selected</span>
            <select value={listId} onChange={(e) => setListId(e.target.value)}>
              <option value="">Choose a list…</option>
              {(lists.data || []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            <button className="btn" disabled={!listId} onClick={addToList}>Add to list</button>
          </div>
        )}
        <Notice>{note}</Notice>
      </section>
      <NewContact onCreated={reload} />
      {user.isAdmin && <ImportContacts onImported={reload} />}
    </div>
  );
}
