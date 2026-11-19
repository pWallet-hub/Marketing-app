import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { Empty, Icon, Loading, Modal, Notice, PageHead, formatDay, useConfirm, useLoader, useToast } from '../ui.jsx';

function Thumb() {
  return (
    <div className="thumb" aria-hidden="true">
      <i style={{ top: 30, right: '40%' }} /><i style={{ top: 44 }} /><i style={{ top: 56, right: '25%' }} />
      <i style={{ top: 72, left: 12, right: 'auto', width: 64, height: 12, background: 'var(--primary)', opacity: 0.7 }} />
    </div>
  );
}

export function StarterPicker({ onClose }) {
  const navigate = useNavigate();
  const starters = useLoader(() => api('/templates/starters'), []);
  return (
    <Modal title="Start a new template" wide onClose={onClose}>
      <p className="muted" style={{ marginTop: 0 }}>Choose a starting design. Everything can be changed in the editor.</p>
      {starters.loading ? <Loading /> : (
        <div className="gallery">
          {(starters.data || []).map((s) => (
            <button key={s.key} className="tile" onClick={() => navigate(`/templates/new?starter=${s.key}`)}>
              <Thumb />
              <strong>{s.name}</strong>
              <span className="muted small">{s.description}</span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}

export default function Templates() {
  const toast = useToast();
  const navigate = useNavigate();
  const [confirm, dialog] = useConfirm();
  const templates = useLoader(() => api('/templates'), []);
  const [picking, setPicking] = useState(false);
  const [q, setQ] = useState('');

  async function duplicate(t) {
    try {
      const copy = await api(`/templates/${t.id}/duplicate`, { method: 'POST' });
      toast(`Copied as “${copy.name}”.`);
      navigate(`/templates/${copy.id}`);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function remove(t) {
    if (!(await confirm({ title: `Delete “${t.name}”?`, message: 'This cannot be undone.', confirmLabel: 'Delete', danger: true }))) return;
    try {
      await api(`/templates/${t.id}`, { method: 'DELETE' });
      toast('Template deleted.');
      templates.reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const visible = (templates.data || []).filter((t) => !q || `${t.name} ${t.subject}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="stack">
      <PageHead
        title="Templates"
        subtitle="Reusable email designs. Every email is wrapped in the AFS header and footer with an unsubscribe link."
        actions={<button className="btn btn-primary" onClick={() => setPicking(true)}><Icon name="plus" />New template</button>}
      />
      {templates.loading && <Loading />}
      <Notice kind="error">{templates.error}</Notice>
      {templates.data && templates.data.length === 0 && (
        <section className="card">
          <Empty icon="template" title="No templates yet" action={<button className="btn btn-primary" onClick={() => setPicking(true)}>Start from a design</button>}>
            Newsletter, announcement, event invitation, media invitation and information request designs are ready to use.
          </Empty>
        </section>
      )}
      {templates.data && templates.data.length > 0 && (
        <>
          <div className="toolbar"><div className="grow"><input type="search" placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
          <div className="gallery">
            {visible.map((t) => (
              <div key={t.id} className="tile" style={{ cursor: 'default' }}>
                <Link to={`/templates/${t.id}`} aria-label={`Edit ${t.name}`}><Thumb /></Link>
                <Link to={`/templates/${t.id}`} className="row-link">{t.name}</Link>
                <span className="muted small" style={{ overflowWrap: 'anywhere' }}>{t.subject}</span>
                <span className="faint small">Edited {formatDay(t.updated_at)}{t.used_by ? ` · used by ${t.used_by} campaign${t.used_by === 1 ? '' : 's'}` : ''}</span>
                <div className="btn-group">
                  <Link className="btn btn-sm" to={`/templates/${t.id}`}><Icon name="edit" size={14} />Edit</Link>
                  <button className="btn btn-sm" onClick={() => duplicate(t)}><Icon name="copy" size={14} />Copy</button>
                  {!t.used_by && <button className="btn btn-sm btn-ghost" onClick={() => remove(t)} aria-label={`Delete ${t.name}`}><Icon name="trash" size={14} /></button>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      {picking && <StarterPicker onClose={() => setPicking(false)} />}
      {dialog}
    </div>
  );
}
