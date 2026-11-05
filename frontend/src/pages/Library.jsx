import { useState } from 'react';
import { api } from '../api.js';
import { Field, Loading, Notice, useLoader } from '../ui.jsx';

const PLACEHOLDERS = ['{{name}}', '{{organisation}}', '{{email}}', '{{unsubscribe_url}}', '{{form_url}}'];
const EMPTY_TEMPLATE = { id: null, name: '', subject: '', body_html: '<p>Dear {{name}},</p>\n<p></p>' };

function Lists({ canEdit }) {
  const lists = useLoader(() => api('/lists'), []);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  async function create(event) {
    event.preventDefault();
    setError('');
    try {
      await api('/lists', { method: 'POST', body: { name, description } });
      setName('');
      setDescription('');
      lists.reload();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <h2>Lists</h2>
      {lists.loading && <Loading />}
      <Notice kind="error">{lists.error}</Notice>
      {lists.data && (
        lists.data.length === 0 ? <p className="muted">No lists yet.</p> : (
          <table>
            <thead><tr><th>Name</th><th>Members</th><th>Description</th></tr></thead>
            <tbody>
              {lists.data.map((l) => <tr key={l.id}><td>{l.name}</td><td>{l.members}</td><td>{l.description}</td></tr>)}
            </tbody>
          </table>
        )
      )}
      {canEdit && (
        <form className="grid" onSubmit={create}>
          <Field label="Name"><input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Description"><input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <div className="actions"><button className="btn btn-primary">Create list</button></div>
        </form>
      )}
      <Notice kind="error">{error}</Notice>
      <p className="muted">To add people, select them on the Contacts page and choose a list.</p>
    </section>
  );
}

function Templates({ canEdit }) {
  const templates = useLoader(() => api('/templates'), []);
  const [editing, setEditing] = useState(null);
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState({ kind: '', text: '' });

  async function save(event) {
    event.preventDefault();
    setMessage({ kind: '', text: '' });
    const body = { name: editing.name, subject: editing.subject, body_html: editing.body_html };
    try {
      if (editing.id) await api(`/templates/${editing.id}`, { method: 'PUT', body });
      else await api('/templates', { method: 'POST', body });
      setMessage({ kind: 'success', text: 'Template saved.' });
      setEditing(null);
      templates.reload();
    } catch (err) {
      setMessage({ kind: 'error', text: err.message });
    }
  }

  async function showPreview(template) {
    const result = await api(`/templates/${template.id}/preview`, { method: 'POST', body: {} });
    setPreview(result);
  }

  return (
    <section className="card">
      <h2>Email templates</h2>
      {templates.loading && <Loading />}
      <Notice kind="error">{templates.error}</Notice>
      {templates.data && (
        <table>
          <thead><tr><th>Name</th><th>Subject</th><th></th></tr></thead>
          <tbody>
            {templates.data.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td>{t.subject}</td>
                <td className="actions">
                  <button className="btn" onClick={() => showPreview(t)}>Preview</button>
                  {canEdit && <button className="btn" onClick={() => setEditing({ ...t })}>Edit</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && !editing && <button className="btn btn-primary" onClick={() => setEditing({ ...EMPTY_TEMPLATE })}>New template</button>}
      {editing && (
        <form className="stack" onSubmit={save}>
          <h3>{editing.id ? 'Edit template' : 'New template'}</h3>
          <Field label="Name"><input required value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></Field>
          <Field label="Subject" hint="Placeholders work here too."><input required value={editing.subject} onChange={(e) => setEditing({ ...editing, subject: e.target.value })} /></Field>
          <Field label="Body (HTML)" hint={`Placeholders: ${PLACEHOLDERS.join(' ')}. Every email gets an unsubscribe link at the foot.`}>
            <textarea rows="12" required value={editing.body_html} onChange={(e) => setEditing({ ...editing, body_html: e.target.value })} />
          </Field>
          <div className="actions">
            <button className="btn btn-primary">Save</button>
            <button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>
      )}
      <Notice kind={message.kind}>{message.text}</Notice>
      {preview && (
        <div className="preview">
          <h3>Preview</h3>
          <p><strong>Subject:</strong> {preview.subject}</p>
          <iframe title="Email preview" sandbox="" srcDoc={preview.html} className="preview-frame" />
          <button className="btn" onClick={() => setPreview(null)}>Close preview</button>
        </div>
      )}
    </section>
  );
}

// Administrators and members can both draft lists and templates. Only administrators send.
export default function Library() {
  return (
    <div className="stack">
      <h1>Lists &amp; templates</h1>
      <Lists canEdit />
      <Templates canEdit />
    </div>
  );
}
