import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api.js';
import { Field, Loading, Notice } from '../ui.jsx';

// These pages are opened from emails, so they do not need a sign-in.

function PublicPage({ children }) {
  return (
    <div className="public-page">
      <div className="public">
        <div className="public-brand"><span className="brand-mark">AFS</span>Alliance for Science Rwanda</div>
        <div className="card">{children}</div>
      </div>
    </div>
  );
}

export function Unsubscribe() {
  const { token } = useParams();
  const [status, setStatus] = useState('ready'); // ready | working | done | error
  const [message, setMessage] = useState('');

  async function confirm() {
    setStatus('working');
    try {
      await api('/public/unsubscribe', { method: 'POST', body: { token } });
      setStatus('done');
    } catch (err) {
      setStatus('error');
      setMessage(err.message);
    }
  }

  return (
    <PublicPage>
      <h1>Unsubscribe</h1>
      {status === 'ready' && (
        <>
          <p>Select the button below to stop receiving these emails from AFS.</p>
          <button className="btn btn-primary" onClick={confirm}>Unsubscribe me</button>
        </>
      )}
      {status === 'working' && <Loading label="Updating your preferences…" />}
      {status === 'done' && <Notice kind="success">You have been unsubscribed. You will not receive these emails again.</Notice>}
      {status === 'error' && <Notice kind="error">{message}</Notice>}
    </PublicPage>
  );
}

const LABELS = {
  name: 'Full name',
  organisation: 'Organisation',
  position: 'Position or role',
  phone: 'Phone number',
  procurement_contact: 'Procurement contact (name or email)',
  notes: 'Anything else we should know',
};

export function InfoForm() {
  const { token } = useParams();
  const [form, setForm] = useState(null);
  const [values, setValues] = useState({});
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api(`/public/forms/${token}`)
      .then((data) => {
        if (!active) return;
        setForm(data);
        setValues({ name: data.name || '', organisation: data.organisation || '' });
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/public/forms/${token}`, { method: 'POST', body: values });
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading />;
  if (done) return <PublicPage><Notice kind="success">Thank you. Your details have been received.</Notice></PublicPage>;
  if (!form) return <PublicPage><Notice kind="error">{error}</Notice></PublicPage>;

  return (
    <PublicPage>
      <h1>Update your details</h1>
      <p>Please check and complete the details below. This link can be used once.</p>
      {error && <Notice kind="error">{error}</Notice>}
      <form onSubmit={submit} className="stack">
        {form.fields.map((key) => (
          <Field key={key} label={LABELS[key] || key}>
            {key === 'notes'
              ? <textarea rows="4" value={values[key] || ''} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
              : <input value={values[key] || ''} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />}
          </Field>
        ))}
        <button className="btn btn-primary" disabled={busy}>{busy ? 'Sending…' : 'Submit'}</button>
      </form>
    </PublicPage>
  );
}
