import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import {
  Badge, Empty, Field, Icon, Loading, Modal, Notice, PageHead, Pager, Stat, TYPE_LABEL, useConfirm, useDebounced, useLoader, useToast,
} from '../ui.jsx';
import { ListModal } from './Lists.jsx';
import { NewCampaignModal } from './Campaigns.jsx';

const LIMIT = 50;

function AddByFilterModal({ list, onClose, onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ q: '', type: '', status: '', consent: 'marketing' });
  const query = useDebounced(f.q);
  const params = new URLSearchParams(Object.entries({ ...f, q: query }).filter(([, v]) => v));
  const count = useLoader(() => api(`/contacts?${params}&limit=1`), [query, f.type, f.status, f.consent]);
  const set = (key) => (e) => setF({ ...f, [key]: e.target.value });

  async function add() {
    try {
      const r = await api(`/lists/${list.id}/members/by-filter`, { method: 'POST', body: { ...f, q: query } });
      toast(`Added ${r.added} contacts to “${list.name}”.`);
      onDone();
      onClose();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <Modal title={`Add contacts to “${list.name}”`} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={add} disabled={!count.data?.total}>Add {count.data?.total ?? ''} contacts</button></>}>
      <div className="stack">
        <p className="muted" style={{ margin: 0 }}>Everyone who matches is added. People already on the list are left as they are.</p>
        <Field label="Search"><input value={f.q} onChange={set('q')} placeholder="Name, email or organisation (optional)" /></Field>
        <div className="form-grid">
          <Field label="Type">
            <select value={f.type} onChange={set('type')}>
              <option value="">All types</option><option value="media">Media</option><option value="partner">Partners</option><option value="staff">Staff</option>
            </select>
          </Field>
          <Field label="Consent">
            <select value={f.consent} onChange={set('consent')}>
              <option value="">Any</option><option value="marketing">Agreed to marketing</option><option value="information_request">Agreed to info requests</option>
            </select>
          </Field>
        </div>
        <Notice kind="info">{count.loading ? 'Counting…' : `${count.data?.total ?? 0} contacts match.`}</Notice>
      </div>
    </Modal>
  );
}

export default function ListDetail() {
  const { id } = useParams();
  const user = useUser();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirm, dialog] = useConfirm();
  const list = useLoader(() => api(`/lists/${id}`), [id]);
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const [modal, setModal] = useState('');
  const query = useDebounced(q);
  const members = useLoader(
    () => api(`/contacts?${new URLSearchParams({ list_id: id, q: query, limit: LIMIT, offset })}`),
    [id, query, offset],
  );

  if (list.loading && !list.data) return <Loading />;
  if (list.error) return <Notice kind="error">{list.error}</Notice>;
  const l = list.data;
  const refresh = () => { list.reload(); members.reload(); };

  async function removeMember(contact) {
    try {
      await api(`/lists/${id}/members/${contact.id}`, { method: 'DELETE' });
      toast(`Removed ${contact.name || contact.email}.`);
      refresh();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function remove() {
    if (!(await confirm({ title: `Delete “${l.name}”?`, message: 'The list is deleted. The contacts on it are kept.', confirmLabel: 'Delete list', danger: true }))) return;
    try {
      await api(`/lists/${id}`, { method: 'DELETE' });
      toast('List deleted.');
      navigate('/lists');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <div className="stack">
      <PageHead
        crumbs={<Link to="/lists"><Icon name="arrowLeft" size={12} /> Lists</Link>}
        title={l.name}
        subtitle={l.description || 'No description'}
        actions={(
          <>
            <button className="btn btn-ghost" onClick={remove}><Icon name="trash" />Delete</button>
            <button className="btn" onClick={() => setModal('edit')}><Icon name="edit" />Edit</button>
            {user.isAdmin && <a className="btn" href={`/api/contacts/export?list_id=${id}`}><Icon name="download" />Export</a>}
            <button className="btn btn-primary" onClick={() => setModal('campaign')}><Icon name="send" />Send a campaign</button>
          </>
        )}
      />
      <div className="stats">
        <Stat label="Contacts" value={l.members} />
        <Stat label="Can receive marketing" value={l.with_marketing_consent} rate={l.members ? (100 * l.with_marketing_consent) / l.members : 0} />
        <Stat label="Can receive info requests" value={l.with_information_consent} rate={l.members ? (100 * l.with_information_consent) / l.members : 0} />
      </div>
      <section className="card card-flush">
        <div className="card-head">
          <h2>Members</h2>
          <div className="btn-group">
            <Link className="btn btn-sm" to="/contacts">Pick from contacts</Link>
            <button className="btn btn-sm btn-primary" onClick={() => setModal('filter')}><Icon name="plus" size={14} />Add by filter</button>
          </div>
        </div>
        <div style={{ padding: '10px 18px 0' }}>
          <div className="toolbar"><div className="grow"><input type="search" placeholder="Search this list" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} /></div></div>
        </div>
        {members.loading && !members.data && <Loading />}
        {members.data && members.data.items.length === 0 && (
          <Empty icon="users" title={q ? 'Nobody matches' : 'This list is empty'}
            action={!q && <button className="btn btn-primary" onClick={() => setModal('filter')}>Add contacts</button>}>
            {q ? 'Try another search.' : 'Add everyone who matches a filter, or pick people on the Contacts page.'}
          </Empty>
        )}
        {members.data && members.data.items.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Contact</th><th className="hide-sm">Type</th><th className="hide-sm">Consent</th><th>Status</th><th /></tr></thead>
              <tbody>
                {members.data.items.map((c) => (
                  <tr key={c.id}>
                    <td><Link className="row-link" to={`/contacts/${c.id}`}>{c.name || c.email}</Link>{c.name && <span className="sub">{c.email}</span>}</td>
                    <td className="hide-sm">{TYPE_LABEL[c.type]}</td>
                    <td className="hide-sm">
                      {c.marketing_consent && <Badge value="yes" label="Marketing" />}{' '}
                      {c.information_consent && <Badge value="yes" label="Info" />}
                      {!c.marketing_consent && !c.information_consent && <span className="faint small">None</span>}
                    </td>
                    <td><Badge value={c.status} /></td>
                    <td className="right"><button className="btn btn-sm btn-ghost" onClick={() => removeMember(c)} aria-label={`Remove ${c.email}`}>Remove</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager total={members.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </section>
      {modal === 'edit' && <ListModal initial={l} onClose={() => setModal('')} onSaved={() => { setModal(''); list.reload(); }} />}
      {modal === 'filter' && <AddByFilterModal list={l} onClose={() => setModal('')} onDone={refresh} />}
      {modal === 'campaign' && <NewCampaignModal initial={{ list_id: String(l.id) }} onClose={() => setModal('')} />}
      {dialog}
    </div>
  );
}
