import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { Empty, Field, Icon, Loading, Modal, Notice, PageHead, formatDay, useLoader, useToast } from '../ui.jsx';

export function ListModal({ initial, onClose, onSaved }) {
  const toast = useToast();
  const [name, setName] = useState(initial?.name || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setError('');
    try {
      const saved = initial
        ? await api(`/lists/${initial.id}`, { method: 'PATCH', body: { name, description } })
        : await api('/lists', { method: 'POST', body: { name, description } });
      toast(initial ? 'List updated.' : 'List created.');
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Modal title={initial ? 'Edit list' : 'New list'} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="list-form">{initial ? 'Save' : 'Create list'}</button></>}>
      <form id="list-form" className="stack" onSubmit={submit}>
        <Field label="Name"><input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kigali journalists" /></Field>
        <Field label="Description" hint="Optional: who is on it and why."><input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Notice kind="error">{error}</Notice>
      </form>
    </Modal>
  );
}

export default function Lists() {
  const navigate = useNavigate();
  const lists = useLoader(() => api('/lists'), []);
  const [creating, setCreating] = useState(false);

  return (
    <div className="stack">
      <PageHead
        title="Lists"
        subtitle="Groups of contacts to send campaigns to. Only people who agreed to the campaign’s purpose receive it."
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}><Icon name="plus" />New list</button>}
      />
      <section className="card card-flush">
        {lists.loading && <Loading />}
        <Notice kind="error">{lists.error}</Notice>
        {lists.data && lists.data.length === 0 && (
          <Empty icon="list" title="No lists yet" action={<button className="btn btn-primary" onClick={() => setCreating(true)}>Create a list</button>}>
            Create a list, then add contacts from the Contacts page: pick them one by one, or add everyone who matches a filter.
          </Empty>
        )}
        {lists.data && lists.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>List</th><th className="right">Contacts</th><th className="hide-sm">Created</th></tr></thead>
              <tbody>
                {lists.data.map((l) => (
                  <tr key={l.id}>
                    <td><Link className="row-link" to={`/lists/${l.id}`}>{l.name}</Link>{l.description && <span className="sub">{l.description}</span>}</td>
                    <td className="right">{l.members}</td>
                    <td className="hide-sm">{formatDay(l.created_at)}<span className="sub">{l.created_by}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {creating && <ListModal onClose={() => setCreating(false)} onSaved={(l) => navigate(`/lists/${l.id}`)} />}
    </div>
  );
}
