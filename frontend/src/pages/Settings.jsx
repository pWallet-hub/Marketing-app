import { api } from '../api.js';
import { useUser } from '../session.js';
import { Badge, Loading, Notice, PageHead, useLoader } from '../ui.jsx';

function Row({ label, ok, children }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{ok !== undefined && <Badge value={ok ? 'yes' : 'no'} label={ok ? 'Connected' : 'Not set up'} />} {children}</dd>
    </>
  );
}

export default function Settings() {
  const user = useUser();
  const { data, error, loading } = useLoader(() => api('/settings'), []);
  if (loading) return <Loading />;
  if (error) return <Notice kind="error">{error}</Notice>;
  return (
    <div className="stack">
      <PageHead title="Settings" subtitle="How this app sends email. These values are set by your system administrator in the deployment." />
      <div className="cols-even">
        <section className="card">
          <h2>Sending</h2>
          <dl className="kv">
            <Row label="Email service (Resend)" ok={data.mail_configured} />
            <Row label="Sender">{data.from || <span className="faint">Not set</span>}</Row>
            <Row label="Delivery reports" ok={data.webhook_configured}>
              <div className="faint small">Bounces, complaints, opens and clicks.</div>
            </Row>
            <Row label="Biocap blog accounts" ok={data.blog_accounts_configured} />
            <Row label="Form forwarding" ok={data.form_forwarding_configured}>
              <div className="faint small">Without it, form answers are kept in this app.</div>
            </Row>
          </dl>
        </section>
        <section className="card">
          <h2>Branding in emails</h2>
          <dl className="kv">
            <Row label="Organisation">{data.org_name}</Row>
            <Row label="Postal address">{data.org_address || <span className="faint">Not set (recommended for marketing email)</span>}</Row>
            <Row label="Website">{data.org_website || <span className="faint">Not set</span>}</Row>
            <Row label="Brand colour">
              <span style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 4, background: data.brand_color, verticalAlign: -2, marginRight: 6 }} />
              {data.brand_color}
            </Row>
          </dl>
        </section>
      </div>
      <section className="card">
        <h2>Your access</h2>
        <p style={{ margin: 0 }}>
          You are signed in as <strong>{user.email}</strong> with the <strong>{user.role}</strong> role, given in AFS Command Center.
          {user.isAdmin
            ? ' Administrators can import and export contacts, send and schedule campaigns, and manage the do-not-contact list.'
            : ' Members can manage contacts, lists and templates and prepare campaigns. An administrator sends them.'}
        </p>
      </section>
      {user.isAdmin && (
        <Notice kind="info">
          Open and click tracking must also be switched on for the sending domain in Resend (Domains → Configuration),
          and the webhook registered at <code>{data.public_base_url}/api/webhooks/resend</code>.
        </Notice>
      )}
    </div>
  );
}
