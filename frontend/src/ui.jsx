import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

// ---------- Icons (inline SVG, 24px grid, stroke) ----------
const PATHS = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  send: 'M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z',
  users: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm14 10v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  template: 'M4 4h16v16H4zM4 9h16M9 9v11',
  block: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM4.93 4.93l14.14 14.14',
  activity: 'M22 12h-4l-3 9L9 3l-3 9H2',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.6 7.6 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.6 7.6 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z',
  plus: 'M12 5v14M5 12h14',
  menu: 'M3 6h18M3 12h18M3 18h18',
  close: 'M18 6 6 18M6 6l12 12',
  mail: 'M4 4h16v16H4zM4 6l8 7 8-7',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zm0-16v6l4 2',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  trash: 'M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14',
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z',
  eye: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zm11 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  download: 'M21 15v4H3v-4M7 10l5 5 5-5M12 15V3',
  upload: 'M21 15v4H3v-4M17 8l-5-5-5 5M12 3v12',
  check: 'M20 6 9 17l-5-5',
  alert: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zm0-6v-4m0-4h.01',
  chart: 'M3 3v18h18M7 16v-5m5 5V8m5 8v-3',
  link: 'M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm10 2-4.3-4.3',
  arrowLeft: 'M19 12H5m7 7-7-7 7-7',
  monitor: 'M2 4h20v12H2zM8 20h8M12 16v4',
  phone: 'M7 2h10v20H7zM11 18h2',
};

export function Icon({ name, size = 18, className = '' }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || PATHS.info} />
    </svg>
  );
}

// ---------- Feedback ----------
const NOTICE_ICONS = { info: 'info', success: 'check', error: 'alert', warning: 'alert' };

export function Notice({ kind = 'info', children }) {
  if (!children) return null;
  return (
    <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <Icon name={NOTICE_ICONS[kind]} size={16} />
      <div>{children}</div>
    </div>
  );
}

export function Loading({ label = 'Loading…' }) {
  return <div className="loading"><span className="spinner" />{label}</div>;
}

export function Empty({ icon = 'mail', title, children, action }) {
  return (
    <div className="empty">
      <Icon name={icon} size={36} />
      {title && <h3>{title}</h3>}
      {children && <p>{children}</p>}
      {action && <div className="actions">{action}</div>}
    </div>
  );
}

const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((text, kind = 'success') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 7000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <Icon name={NOTICE_ICONS[t.kind] || 'info'} size={16} />
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function Modal({ title, onClose, children, footer, wide = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    ref.current?.querySelector('input, select, textarea, button')?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

// A confirmation dialog as a hook: const [confirm, dialog] = useConfirm(); ... if (await confirm({...})) ...
export function useConfirm() {
  const [state, setState] = useState(null);
  const confirm = useCallback(
    (options) => new Promise((resolve) => setState({ ...options, resolve })),
    [],
  );
  const close = (answer) => {
    state?.resolve(answer);
    setState(null);
  };
  const dialog = state && (
    <Modal
      title={state.title || 'Are you sure?'}
      onClose={() => close(false)}
      footer={(
        <>
          <button className="btn" onClick={() => close(false)}>Cancel</button>
          <button className={`btn ${state.danger ? 'btn-danger' : 'btn-primary'}`} onClick={() => close(true)}>
            {state.confirmLabel || 'Confirm'}
          </button>
        </>
      )}
    >
      <p style={{ margin: 0 }}>{state.message}</p>
    </Modal>
  );
  return [confirm, dialog];
}

// ---------- Layout helpers ----------
export function PageHead({ title, subtitle, crumbs, actions }) {
  return (
    <div className="page-head">
      <div>
        {crumbs && <div className="crumbs">{crumbs}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="btn-group">{actions}</div>}
    </div>
  );
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

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} className={value === t.value ? 'active' : ''}
          onClick={() => onChange(t.value)}>
          {t.label}{t.count !== undefined && <span className="count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

const BADGE_LABELS = { information_request: 'information', not_configured: 'not configured' };

export function Badge({ value, label }) {
  const text = label || BADGE_LABELS[value] || String(value).replace(/_/g, ' ');
  return <span className={`badge badge-${value}`}>{text}</span>;
}

export function Stat({ label, value, sub, rate }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
      {rate !== undefined && <div className="meter"><span style={{ width: `${Math.min(100, rate)}%` }} /></div>}
    </div>
  );
}

export function Pager({ total, limit, offset, onChange }) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="pager">
      <span className="muted small">{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
      <div className="btn-group">
        <button className="btn btn-sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
        <span className="muted small">Page {page} of {pages}</span>
        <button className="btn btn-sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
      </div>
    </div>
  );
}

// Two series of daily bars (e.g. sent and opened), with a light grid and sparse date labels.
export function BarChart({ data, a, b, labelA, labelB, height = 180 }) {
  const width = 640;
  const pad = { l: 28, r: 6, t: 8, b: 22 };
  const max = Math.max(1, ...data.map((d) => Math.max(d[a] || 0, b ? d[b] || 0 : 0)));
  const step = (width - pad.l - pad.r) / Math.max(1, data.length);
  const barW = Math.max(2, (step - 3) / (b ? 2 : 1));
  const y = (v) => pad.t + (height - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, Math.ceil(max / 2), max];
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${labelA}${b ? ` and ${labelB}` : ''} per day`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-line" x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} />
            <text className="axis" x={pad.l - 6} y={y(t) + 3} textAnchor="end">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = pad.l + i * step + 1.5;
          return (
            <g key={d.day}>
              <rect className="bar-a" x={x} y={y(d[a] || 0)} width={barW} height={height - pad.b - y(d[a] || 0)} rx="1.5">
                <title>{`${d.day}: ${d[a] || 0} ${labelA.toLowerCase()}`}</title>
              </rect>
              {b && (
                <rect className="bar-b" x={x + barW} y={y(d[b] || 0)} width={barW} height={height - pad.b - y(d[b] || 0)} rx="1.5">
                  <title>{`${d.day}: ${d[b] || 0} ${labelB.toLowerCase()}`}</title>
                </rect>
              )}
              {(i % 7 === 0 || i === data.length - 1) && (
                <text className="axis" x={x + barW} y={height - 6} textAnchor="middle">
                  {new Date(d.day).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><i style={{ background: 'var(--chart-1)' }} />{labelA}</span>
        {b && <span><i style={{ background: 'var(--chart-2)' }} />{labelB}</span>}
      </div>
    </div>
  );
}

// ---------- Data ----------
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

export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatDay(value) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export function pct(value) {
  return `${Number(value || 0).toFixed(1).replace(/\.0$/, '')}%`;
}

export const PURPOSE_LABEL = { marketing: 'Marketing', information_request: 'Information request' };
export const TYPE_LABEL = { media: 'Media', partner: 'Partner', staff: 'Staff' };
