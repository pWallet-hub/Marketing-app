import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import {
  Badge, Empty, Field, Icon, Loading, Modal, Notice, PageHead, Pager, formatDate, useConfirm, useDebounced, useLoader, useToast,
} from '../ui.jsx';

const LIMIT = 50;
const REASON_HELP = {
  unsubscribed: 'They clicked unsubscribe',
  complained: 'They marked an email as spam',
  bounced: 'The address does not accept mail',
  erased: 'Deleted on request',
  manual: 'Added by an administrator',
};
const PURPOSE = { all: 'All email', marketing: 'Marketing', information_request: 'Information requests' };

export default function Suppressions() {
  const user = useUser();
  const toast = useToast();
  const [confirm, dialog] = useConfirm();
  const [q, setQ] = useState('');
  const [reason, setReason] = useState('');
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ email: '', purpose: 'all' });
  const query = useDebounced(q);
  const data = useLoader(() => api(`/suppressions?${new URLSearchParams({ q: query, reason, limit: LIMIT, offset })}`), [query, reason, offset]);

  async function add(event) {
    event.preventDefault();
    try {
      await api('/suppressions', { method: 'POST', body: form });
      toast(`${form.email} will not be emailed.`);
      setAdding(false);
      setForm({ email: '', purpose: 'all' });
      data.reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function remove(row) {
    const ok = await confirm({
      title: `Allow email to ${row.email} again?`,
      message: row.reason === 'bounced' ? 'Only do this if the address has been fixed. Repeated bounces harm delivery for everyone.' : 'They will be able to receive email they have agreed to.',
      confirmLabel: 'Remove block',
    });
    if (!ok) return;
    try {
      await api(`/suppressions/${row.id}`, { method: 'DELETE' });
      toast('Block removed.');
      data.reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const reasons = data.data?.reasons || {};
  return (
    <div className="stack">
      <PageHead
        title="Do not contact"
        subtitle="Addresses that never receive email, whatever list they are on. Checked before every send."
        actions={user.isAdmin && <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" />Block an address</button>}
      />
      <section className="card card-flush">
        <div style={{ padding: '14px 18px 0' }}>
          <div className="toolbar">
            <div className="grow"><input type="search" placeholder="Search addresses" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} /></div>
            <select value={reason} onChange={(e) => { setReason(e.target.value); setOffset(0); }} aria-label="Reason">
              <option value="">All reasons</option>
              {Object.keys(REASON_HELP).map((r) => <option key={r} value={r}>{r} ({reasons[r] || 0})</option>)}
            </select>
          </div>
        </div>
        {data.loading && !data.data && <Loading />}
        <Notice kind="error">{data.error}</Notice>
        {data.data && data.data.items.length === 0 && <Empty icon="block" title="No blocked addresses">Unsubscribes, bounces and spam complaints appear here automatically.</Empty>}
        {data.data && data.data.items.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Address</th><th>Reason</th><th className="hide-sm">Applies to</th><th className="hide-sm">Since</th><th /></tr></thead>
              <tbody>
                {data.data.items.map((s) => (
                  <tr key={s.id}>
                    <td>{s.contact_id ? <Link className="row-link" to={`/contacts/${s.contact_id}`}>{s.email}</Link> : s.email}{s.contact_name && <span className="sub">{s.contact_name}</span>}</td>
                    <td><Badge value={s.reason} /><span className="sub">{REASON_HELP[s.reason]}</span></td>
                    <td className="hide-sm">{PURPOSE[s.purpose]}</td>
                    <td className="hide-sm">{formatDate(s.created_at)}</td>
                    <td className="right">{user.isAdmin && s.removable && <button className="btn btn-sm" onClick={() => remove(s)}>Remove</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager total={data.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </section>
      <p className="faint small">Unsubscribes, spam complaints and deletions cannot be undone here: only the person can opt in again.</p>
      {adding && (
        <Modal title="Block an address" onClose={() => setAdding(false)}
          footer={<><button className="btn" onClick={() => setAdding(false)}>Cancel</button><button className="btn btn-primary" form="block-form">Block</button></>}>
          <form id="block-form" className="stack" onSubmit={add}>
            <Field label="Email address"><input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Block">
              <select value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
                <option value="all">All email</option><option value="marketing">Marketing only</option><option value="information_request">Information requests only</option>
              </select>
            </Field>
          </form>
        </Modal>
      )}
      {dialog}
    </div>
  );
}
