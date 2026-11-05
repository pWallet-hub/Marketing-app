import { useEffect, useState } from 'react';

export function Notice({ kind = 'info', children }) {
  if (!children) return null;
  return <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>;
}

export function Loading({ label = 'Loading…' }) {
  return <p className="muted">{label}</p>;
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

export function Badge({ value }) {
  return <span className={`badge badge-${value}`}>{String(value).replace(/_/g, ' ')}</span>;
}

export function Pager({ total, limit, offset, onChange }) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="pager">
      <button className="btn" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <span className="muted">Page {page} of {pages} ({total} total)</span>
      <button className="btn" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}

// Runs an async loader when `deps` change. Gives the data, an error message, and a reload function.
export function useLoader(loader, deps) {
  const [state, setState] = useState({ data: null, error: '', loading: true });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setState((s) => ({ ...s, loading: true }));
    loader()
      .then((data) => active && setState({ data, error: '', loading: false }))
      .catch((err) => active && setState({ data: null, error: err.message, loading: false }));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version]);
  return { ...state, reload: () => setVersion((v) => v + 1) };
}

export function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}
