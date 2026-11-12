import type { PayPalTx } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { DataTable } from '@/components/ui/table';
import { dateTime } from '@/lib/utils';

export function PayPalLog({ rows }: { rows: PayPalTx[] }) {
  return (
    <DataTable rows={rows} rowKey={(r) => r.id} empty="No PayPal API calls recorded." columns={[
      { key: 'op', header: 'Operation', cell: (r) => <code className="text-xs">{r.operation}</code> },
      { key: 'o', header: 'Outcome', cell: (r) => <Badge tone={r.outcome === 'success' ? 'green' : r.outcome === 'unknown' ? 'amber' : 'red'}>{r.outcome}</Badge> },
      { key: 'h', header: 'HTTP', cell: (r) => r.http_status ?? '—' },
      { key: 'res', header: 'Resource', cell: (r) => <span className="text-xs">{r.resource_id ?? '—'} {r.resource_status && <span className="text-muted">({r.resource_status})</span>}</span> },
      { key: 'dbg', header: 'Debug ID', cell: (r) => <code className="text-xs text-muted">{r.paypal_debug_id ?? '—'}</code> },
      { key: 'e', header: 'Error', cell: (r) => <span className="line-clamp-2 max-w-xs text-xs text-rose-700">{r.error_message ?? ''}</span> },
      { key: 'd', header: 'When', cell: (r) => <span className="text-xs">{dateTime(r.created_at)}{r.duration_ms != null && <span className="text-muted"> · {r.duration_ms}ms</span>}</span> },
    ]} />
  );
}
