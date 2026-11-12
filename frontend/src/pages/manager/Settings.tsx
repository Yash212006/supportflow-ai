import { useState } from 'react';
import { CheckCircle2, XCircle } from 'lucide-react';
import { post, errorMessage } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useApi } from '@/lib/queries';
import type { IntegrationStatus } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import { DataTable } from '@/components/ui/table';
import { KeyValue, PageHeader, Skeleton } from '@/components/ui/misc';
import { useAuth, isManager } from '@/stores/auth';
import { dateTime } from '@/lib/utils';

const Ok = ({ ok, label }: { ok: boolean; label: string }) => (
  <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${ok ? 'text-emerald-700' : 'text-slate-500'}`}>{ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}{label}</span>
);

interface Wh { id: string; event_id: string; event_type: string; resource_id: string | null; status: string; verification_status: string | null; processing_note: string | null; created_at: string }

function LlmTest() {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ ok: boolean; mode: string; detail: string } | null>(null);
  return (
    <div className="mt-4 space-y-2">
      <Button size="sm" variant="secondary" loading={busy} onClick={async () => {
        setBusy(true);
        try { setRes(await post('/api/integrations/test-llm')); } catch (e) { setRes({ ok: false, mode: '', detail: errorMessage(e) }); } finally { setBusy(false); }
      }}>Test AI connection</Button>
      {res && <p className={`break-words text-xs ${res.ok ? 'text-emerald-700' : 'text-rose-700'}`}>{res.ok ? 'Working: ' : 'Failed: '}{res.detail}</p>}
    </div>
  );
}

export default function Settings() {
  const role = useAuth((s) => s.user?.role);
  const { data: s, isLoading } = useApi<IntegrationStatus>(['integrations'], '/api/integrations/status');
  const { data: wh } = useApi<Wh[]>(['webhooks'], isManager(role) ? '/api/paypal/webhooks/events' : null);
  if (isLoading || !s) return <Skeleton className="h-96" />;
  return (
    <div>
      <PageHeader title="Integrations" description="Live configuration status. Secrets are never sent to the browser." />
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader title="PayPal Sandbox" action={<Ok ok={s.paypal.configured} label={s.paypal.configured ? 'Connected' : 'Not configured'} />} />
          <CardBody>
            <KeyValue items={[["Environment", s.paypal.mode], ["Base URL", s.paypal.base_url], ["SDK", s.paypal.sdk], ["Webhooks", s.paypal.webhook_configured ? 'Signature verification on' : 'PAYPAL_WEBHOOK_ID not set']]} />
            {!s.paypal.configured && <p className="mt-4 text-xs text-muted">Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox app credentials) in the backend .env. Until then checkout and refunds report "PayPal not configured" instead of pretending to succeed.</p>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Language model" action={<Ok ok={s.llm.configured} label={s.llm.configured ? s.llm.provider : 'Deterministic fallback'} />} />
          <CardBody>
            <KeyValue items={[["Provider", s.llm.provider], ["Mode", s.llm.mode], ["Embeddings", s.embeddings.model], ["Semantic search", s.embeddings.semantic ? 'Yes' : 'No (lexical hashing)']]} />
            {s.llm.configured && isManager(role) && <LlmTest />}
            {!s.llm.configured && <p className="mt-4 text-xs text-muted">Without an OpenAI or Gemini key the agents use a rule-based classifier and templated replies. Policy, risk and PayPal logic are identical in both modes.</p>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="AG Studio" action={<Ok ok={s.ag_studio.license_configured} label={s.ag_studio.license_configured ? 'Licensed' : 'Evaluation (watermark)'} />} />
          <CardBody><KeyValue items={[["Licence key", s.ag_studio.license_configured ? 'Configured (VITE_AG_LICENSE_KEY)' : 'Missing'], ["AI assistant", s.ag_studio.ai_enabled ? 'Enabled via backend LLM proxy' : 'Needs an LLM key on the backend']]} /></CardBody>
        </Card>
        <Card>
          <CardHeader title="Infrastructure" />
          <CardBody><KeyValue items={[["Redis", s.redis.connected ? 'Connected' : 'Unavailable (in-memory rate limiting)'], ["Database", 'PostgreSQL + pgvector']]} /></CardBody>
        </Card>
        {wh && (
          <Card className="md:col-span-2">
            <CardHeader title="PayPal webhook events" description="Unverified events are stored as rejected and never applied" />
            <DataTable rows={wh} rowKey={(w) => w.id} empty="No webhook events received yet." columns={[
              { key: 't', header: 'Event', cell: (w) => <code className="text-xs">{w.event_type}</code> },
              { key: 'r', header: 'Resource', cell: (w) => <code className="text-xs text-muted">{w.resource_id ?? '—'}</code> },
              { key: 'v', header: 'Signature', cell: (w) => <StatusBadge status={w.verification_status === 'SUCCESS' ? 'APPROVED' : 'REJECTED'} /> },
              { key: 's', header: 'Status', cell: (w) => <StatusBadge status={w.status} /> },
              { key: 'n', header: 'Note', cell: (w) => <span className="line-clamp-1 max-w-xs text-xs text-muted">{w.processing_note}</span> },
              { key: 'd', header: 'Received', cell: (w) => <span className="text-xs">{dateTime(w.created_at)}</span> },
            ]} />
          </Card>
        )}
      </div>
    </div>
  );
}
