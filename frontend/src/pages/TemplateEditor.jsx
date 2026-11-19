import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { Field, Icon, Loading, Modal, Notice, PageHead, Tabs, useConfirm, useDebounced, useToast } from '../ui.jsx';
import { EmailPreview } from './CampaignDetail.jsx';

const PLACEHOLDERS = [
  ['{{name}}', 'Name'],
  ['{{organisation}}', 'Organisation'],
  ['{{email}}', 'Email'],
  ['{{form_url}}', 'Form link (information requests)'],
  ['{{unsubscribe_url}}', 'Unsubscribe link'],
];

const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = (url) => (/^(https?:|mailto:|\{\{)/i.test(url.trim()) ? url.trim() : `https://${url.trim()}`);

// The visual editor: a contentEditable area with a toolbar. The HTML it produces is what gets sent, so inserted
// elements carry inline styles (mail clients ignore stylesheets).
function RichEditor({ value, onChange }) {
  const area = useRef(null);
  const saved = useRef(null);
  const [dialog, setDialog] = useState(null);

  useEffect(() => {
    if (area.current && area.current.innerHTML !== value) area.current.innerHTML = value;
    // Only when the value changes from outside (switching tabs, loading); typing updates it from here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const emit = () => onChange(area.current.innerHTML);
  const exec = (command, arg = null) => {
    area.current.focus();
    restore();
    document.execCommand(command, false, arg);
    emit();
  };
  const remember = () => {
    const sel = window.getSelection();
    if (sel.rangeCount && area.current.contains(sel.anchorNode)) saved.current = sel.getRangeAt(0).cloneRange();
  };
  const restore = () => {
    if (!saved.current) return;
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(saved.current);
  };
  const insertHtml = (html) => exec('insertHTML', html);
  const open = (kind) => {
    remember();
    const text = window.getSelection().toString();
    setDialog({ kind, url: kind === 'button' ? 'https://' : '', text, alt: '' });
  };

  function applyDialog() {
    const d = dialog;
    setDialog(null);
    if (!d.url.trim()) return;
    const url = escapeHtml(safeUrl(d.url));
    if (d.kind === 'link') {
      if (d.text && !window.getSelection().toString()) insertHtml(`<a href="${url}">${escapeHtml(d.text)}</a>`);
      else exec('createLink', safeUrl(d.url));
    } else if (d.kind === 'button') {
      insertHtml(`<p style="margin:24px 0"><a href="${url}" style="display:inline-block;background:#1f5fbf;color:#ffffff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:6px">${escapeHtml(d.text || 'Read more')}</a></p><p></p>`);
    } else if (d.kind === 'image') {
      insertHtml(`<p><img src="${url}" alt="${escapeHtml(d.alt)}" style="display:block;max-width:100%;height:auto;border:0;border-radius:6px"></p>`);
    }
  }

  const B = ({ cmd, arg, label, title }) => (
    <button type="button" title={title} aria-label={title} onMouseDown={(e) => e.preventDefault()} onClick={() => exec(cmd, arg)}>{label}</button>
  );

  return (
    <div className="rte">
      <div className="rte-toolbar" role="toolbar" aria-label="Formatting">
        <select aria-label="Text style" onMouseDown={remember} onChange={(e) => { exec('formatBlock', e.target.value); e.target.value = ''; }} defaultValue="">
          <option value="" disabled>Text style</option>
          <option value="p">Paragraph</option>
          <option value="h1">Large heading</option>
          <option value="h2">Heading</option>
          <option value="h3">Small heading</option>
        </select>
        <span className="sep" />
        <B cmd="bold" label={<strong>B</strong>} title="Bold" />
        <B cmd="italic" label={<em>I</em>} title="Italic" />
        <B cmd="underline" label={<u>U</u>} title="Underline" />
        <span className="sep" />
        <B cmd="insertUnorderedList" label="• List" title="Bulleted list" />
        <B cmd="insertOrderedList" label="1. List" title="Numbered list" />
        <B cmd="justifyLeft" label="⇤" title="Align left" />
        <B cmd="justifyCenter" label="↔" title="Centre" />
        <span className="sep" />
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => open('link')} title="Link">Link</button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => open('button')} title="Button">Button</button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => open('image')} title="Image">Image</button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} title="Divider"
          onClick={() => insertHtml('<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0"><p></p>')}>Divider</button>
        <span className="sep" />
        <select aria-label="Insert personal field" onMouseDown={remember} defaultValue=""
          onChange={(e) => { exec('insertText', e.target.value); e.target.value = ''; }}>
          <option value="" disabled>Insert field</option>
          {PLACEHOLDERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <B cmd="removeFormat" label="Clear" title="Clear formatting" />
        <B cmd="undo" label="↶" title="Undo" />
        <B cmd="redo" label="↷" title="Redo" />
      </div>
      <div ref={area} className="rte-area" contentEditable suppressContentEditableWarning
        onInput={emit} onBlur={() => { remember(); emit(); }} onKeyUp={remember} onMouseUp={remember}
        role="textbox" aria-multiline="true" aria-label="Email body" />
      {dialog && (
        <Modal
          title={{ link: 'Insert link', button: 'Insert button', image: 'Insert image' }[dialog.kind]}
          onClose={() => setDialog(null)}
          footer={<><button className="btn" onClick={() => setDialog(null)}>Cancel</button><button className="btn btn-primary" onClick={applyDialog}>Insert</button></>}
        >
          <div className="stack">
            <Field label={dialog.kind === 'image' ? 'Image address (URL)' : 'Web address'}
              hint={dialog.kind === 'image' ? 'Use an image already online (https://…). Keep it under 600px wide.' : 'You can also use {{form_url}}.'}>
              <input value={dialog.url} onChange={(e) => setDialog({ ...dialog, url: e.target.value })} placeholder="https://" />
            </Field>
            {dialog.kind !== 'image' && (
              <Field label={dialog.kind === 'button' ? 'Button text' : 'Text to show'}>
                <input value={dialog.text} onChange={(e) => setDialog({ ...dialog, text: e.target.value })} />
              </Field>
            )}
            {dialog.kind === 'image' && (
              <Field label="Description" hint="Shown when images are blocked, and read aloud by screen readers.">
                <input value={dialog.alt} onChange={(e) => setDialog({ ...dialog, alt: e.target.value })} />
              </Field>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

export default function TemplateEditor() {
  const { id } = useParams();
  const isNew = id === 'new';
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [confirm, dialog] = useConfirm();
  const [form, setForm] = useState(null);
  const [original, setOriginal] = useState('');
  const [error, setError] = useState('');
  const [mode, setMode] = useState('visual');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    let active = true;
    const load = isNew
      ? api('/templates/starters').then((list) => {
        const s = list.find((x) => x.key === params.get('starter')) || list.find((x) => x.key === 'plain');
        return { name: s.key === 'plain' ? '' : s.name, subject: s.subject, preheader: s.preheader, body_html: s.body_html };
      })
      : api(`/templates/${id}`);
    load.then((t) => {
      if (!active) return;
      const value = { name: t.name, subject: t.subject, preheader: t.preheader || '', body_html: t.body_html };
      setForm(value);
      setOriginal(isNew ? '' : JSON.stringify(value));
    }).catch((err) => active && setError(err.message));
    return () => { active = false; };
  }, [id, isNew, params]);

  const draft = useDebounced(form, 400);
  useEffect(() => {
    if (!draft) return;
    let active = true;
    api('/templates/preview', { method: 'POST', body: { subject: draft.subject, preheader: draft.preheader, body_html: draft.body_html } })
      .then((p) => active && setPreview(p))
      .catch(() => {});
    return () => { active = false; };
  }, [draft]);

  useEffect(() => {
    const dirty = form && JSON.stringify(form) !== original;
    const warn = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [form, original]);

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!form) return <Loading />;

  const dirty = JSON.stringify(form) !== original;
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function save(event) {
    event?.preventDefault();
    setBusy(true);
    try {
      if (isNew) {
        const created = await api('/templates', { method: 'POST', body: form });
        setOriginal(JSON.stringify(form));
        toast('Template created.');
        navigate(`/templates/${created.id}`, { replace: true });
      } else {
        await api(`/templates/${id}`, { method: 'PUT', body: form });
        setOriginal(JSON.stringify(form));
        toast('Template saved.');
      }
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!(await confirm({ title: 'Delete this template?', message: 'This cannot be undone.', confirmLabel: 'Delete', danger: true }))) return;
    try {
      await api(`/templates/${id}`, { method: 'DELETE' });
      setOriginal(JSON.stringify(form));
      toast('Template deleted.');
      navigate('/templates');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const unknown = preview?.unknown_placeholders || [];
  return (
    <div className="stack">
      <PageHead
        crumbs={<Link to="/templates"><Icon name="arrowLeft" size={12} /> Templates</Link>}
        title={isNew ? 'New template' : form.name || 'Template'}
        subtitle={dirty ? 'Unsaved changes' : 'All changes saved'}
        actions={(
          <>
            {!isNew && <button className="btn btn-ghost" onClick={remove} disabled={busy}><Icon name="trash" />Delete</button>}
            <button className="btn btn-primary" onClick={save} disabled={busy || !dirty}>{isNew ? 'Create template' : 'Save'}</button>
          </>
        )}
      />
      <div className="editor-layout">
        <form className="stack" onSubmit={save}>
          <section className="card stack">
            <Field label="Template name"><input required value={form.name} onChange={set('name')} placeholder="e.g. Monthly newsletter" /></Field>
            <Field label="Subject line" hint={`${form.subject.length}/200 · Under 60 characters shows in full on most phones.`}>
              <input required maxLength={200} value={form.subject} onChange={set('subject')} placeholder="What the email is about" />
            </Field>
            <Field label="Preview text" hint="The grey line shown after the subject in the inbox. Optional but recommended.">
              <input maxLength={200} value={form.preheader} onChange={set('preheader')} placeholder="A short summary that makes people open it" />
            </Field>
          </section>
          <section className="card">
            <Tabs tabs={[{ value: 'visual', label: 'Visual editor' }, { value: 'html', label: 'HTML' }]} value={mode} onChange={setMode} />
            {mode === 'visual'
              ? <RichEditor key="visual" value={form.body_html} onChange={(body_html) => setForm((f) => ({ ...f, body_html }))} />
              : <textarea className="code rte-html" value={form.body_html} onChange={set('body_html')} spellCheck="false" aria-label="Email HTML" />}
            {unknown.length > 0 && <Notice kind="error">Unknown fields: {unknown.map((u) => `{{${u}}}`).join(', ')}. Use the “Insert field” menu.</Notice>}
            <p className="hint">
              Personal fields such as {'{{name}}'} are filled in for each person. The AFS header, the footer with your
              address and the unsubscribe link are added automatically.
            </p>
          </section>
        </form>
        <section className="card preview-panel"><EmailPreview preview={preview} /></section>
      </div>
      {dialog}
    </div>
  );
}
