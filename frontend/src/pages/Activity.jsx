import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useUser } from '../session.js';
import { Empty, Loading, Notice, PageHead, Pager, formatDate, useLoader } from '../ui.jsx';

const LIMIT = 50;
const GROUPS = [
  ['', 'Everything'],
  ['campaign.', 'Campaigns'],
  ['contact', 'Contacts'],
  ['consent.', 'Consent'],
  ['list.', 'Lists'],
  ['template.', 'Templates'],
  ['suppression.', 'Do not contact'],
  ['media.', 'Media invites'],
];

const LABELS = {
  'campaign.created': 'created a campaign',
  'campaign.updated': 'edited a campaign',
  'campaign.deleted': 'deleted a draft campaign',
  'campaign.sent': 'sent a campaign',
  'campaign.scheduled': 'scheduled a campaign',
  'campaign.unscheduled': 'cancelled a schedule',
  'campaign.test_sent': 'sent a test',
  'contact.created': 'added a contact',
  'contact.updated': 'edited a contact',
  'contact.erased': 'deleted a contact',
  'contacts.imported': 'imported contacts',
  'contacts.exported': 'exported contacts',
  'consent.granted': 'recorded consent',
  'consent.withdrawn': 'withdrew consent',
  'consent.unsubscribed': 'unsubscribed',
  'list.created': 'created a list',
  'list.updated': 'edited a list',
  'list.deleted': 'deleted a list',
  'list.members_added': 'added contacts to a list',
  'list.member_removed': 'removed a contact from a list',
  'template.created': 'created a template',
  'template.updated': 'edited a template',
  'template.deleted': 'deleted a template',
  'suppression.added': 'blocked an address',
  'suppression.removed': 'removed a block',
  'media.invited': 'invited a media contact',
};

function targetLink(target) {
  const [kind, id] = (target || '').split(':');
  const paths = { campaign: 'campaigns', contact: 'contacts', list: 'lists', template: 'templates' };
  if (paths[kind] && id) return <Link to={`/${paths[kind]}/${id}`}>{kind} #{id}</Link>;
  return target || '';
}

function actor(row) {
  if (row.actor_sub === 'public') return 'A recipient';
  if (row.actor_sub === 'resend') return 'Resend';
  if (row.actor_sub === 'scheduler') return 'The scheduler';
  return row.actor_email || 'Someone';
}

export default function Activity() {
  const user = useUser();
  const [group, setGroup] = useState('');
  const [offset, setOffset] = useState(0);
  const log = useLoader(() => api(`/audit?${new URLSearchParams({ action: group, limit: LIMIT, offset })}`), [group, offset]);
  if (!user.isAdmin) return <Notice kind="error">Only administrators can see the activity log.</Notice>;

  return (
    <div className="stack">
      <PageHead title="Activity log" subtitle="Every change in the app, who made it and when. Kept for accountability." />
      <section className="card card-flush">
        <div style={{ padding: '14px 18px 0' }}>
          <div className="toolbar">
            <select value={group} onChange={(e) => { setGroup(e.target.value); setOffset(0); }} aria-label="Show">
              {GROUPS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {log.data && <span className="muted small">{log.data.total} entries</span>}
          </div>
        </div>
        {log.loading && !log.data && <Loading />}
        <Notice kind="error">{log.error}</Notice>
        {log.data && log.data.items.length === 0 && <Empty icon="activity" title="Nothing yet" />}
        {log.data && log.data.items.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>When</th><th>Who</th><th>What</th><th className="hide-sm">Details</th></tr></thead>
              <tbody>
                {log.data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="nowrap">{formatDate(row.at)}</td>
                    <td>{actor(row)}</td>
                    <td>{LABELS[row.action] || row.action} {targetLink(row.target)}</td>
                    <td className="hide-sm faint small"><code>{JSON.stringify(row.detail)}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager total={log.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </section>
    </div>
  );
}
