import { Link, useParams } from 'react-router-dom';
import { Lock, ShieldCheck, Wrench } from 'lucide-react';
import { useApi } from '@/lib/queries';
import type { Execution } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Badge, StatusBadge, SampleBadge } from '@/components/ui/badge';
import { DataTable } from '@/components/ui/table';
import { KeyValue, Notice, PageHeader, Skeleton } from '@/components/ui/misc';
import { DecisionTrace } from '@/components/DecisionTrace';
import { dateTime, humanize } from '@/lib/utils';

const AGENT_LABEL: Record<string, string> = {
  orchestrator: 'Orchestrator', order_investigation: 'Order investigation', policy_intelligence: 'Policy intelligence', risk_assessment: 'Risk assessment', resolution: 'Resolution', manager_copilot: 'Manager copilot', dashboard_agent: 'Dashboard agent (AG Studio)', respond: 'Response',
};

export default function ExecutionDetail() {
  const { id } = useParams();
  const { data: e, isLoading } = useApi<Execution>(['execution', id], `/api/agents/executions/${id}`);
  if (isLoading || !e) return <Skeleton className="h-96" />;
  return (
    <div>
      <PageHeader title={<span className="flex flex-wrap items-center gap-2">{humanize(e.workflow)} run <StatusBadge status={e.status} /> <SampleBadge show={e.is_sample} /></span>} description={`${dateTime(e.created_at)} · ${e.duration_ms ?? '—'} ms · ${e.llm_mode} mode`} />
      {e.error && <Notice tone="danger" className="mb-6" title="Agent error">{e.error}</Notice>}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Agent trace" description="Step summaries recorded by each agent (no hidden chain-of-thought)" />
            <CardBody>
              <ol className="relative space-y-5 border-l border-line pl-6">
                {(e.steps ?? []).map((s, i) => (
                  <li key={i} className="relative">
                    <span className="absolute -left-[31px] grid h-5 w-5 place-items-center rounded-full bg-brand-600 text-[10px] font-semibold text-white">{i + 1}</span>
                    <p className="text-sm"><span className="font-medium">{AGENT_LABEL[s.agent] ?? s.agent}</span> <span className="text-muted">· {humanize(s.step)}</span></p>
                    <p className="mt-0.5 text-sm text-slate-700">{s.summary}</p>
                  </li>
                ))}
              </ol>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={<span className="flex items-center gap-2"><Wrench className="h-4 w-4" /> Tool calls</span>} description="Each agent can only call tools on its allow-list; denied calls are logged" />
            <DataTable rows={e.tool_calls ?? []} rowKey={(t) => t.id} empty="No tool calls." columns={[
              { key: 'a', header: 'Agent', cell: (t) => <span className="text-xs">{AGENT_LABEL[t.agent] ?? t.agent}</span> },
              { key: 't', header: 'Tool', cell: (t) => <code className="text-xs">{t.tool}</code> },
              { key: 'r', header: 'Result', cell: (t) => <span className="line-clamp-2 max-w-xs text-xs text-muted">{t.result_summary}</span> },
              { key: 's', header: '', cell: (t) => (!t.authorized ? <Badge tone="red"><Lock className="h-3 w-3" /> Denied</Badge> : t.success ? <Badge tone="green">OK</Badge> : <Badge tone="red">Error</Badge>) },
              { key: 'd', header: 'ms', align: 'right', cell: (t) => t.duration_ms ?? '—' },
            ]} />
          </Card>
          {e.decisions?.map((d) => (
            <Card key={d.id}>
              <CardHeader title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Policy decision</span>} />
              <CardBody><DecisionTrace decision={d} /></CardBody>
            </Card>
          ))}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Summary" />
            <CardBody className="space-y-4">
              <KeyValue items={[["Intent", humanize(e.intent)], ["Decision", <StatusBadge status={e.decision_outcome} />], ["Autonomous", e.resolved_autonomously ? 'Yes' : 'No'], ["Human needed", e.required_human ? 'Yes' : 'No'], ["Ticket", e.ticket_id ? <Link className="text-brand-600 hover:underline" to={`/manager/tickets/${e.ticket_id}`}>Open</Link> : '—'], ["Order", e.order_id ? <Link className="text-brand-600 hover:underline" to={`/manager/orders/${e.order_id}`}>Open</Link> : '—']]} />
              <div><p className="text-xs text-muted">Input</p><p className="mt-1 text-sm">{e.input_summary}</p></div>
              {e.outcome_summary && <div><p className="text-xs text-muted">Outcome</p><p className="mt-1 whitespace-pre-wrap text-sm">{e.outcome_summary}</p></div>}
            </CardBody>
          </Card>
          {!!e.actions?.length && (
            <Card>
              <CardHeader title="Execution actions" />
              <ul className="divide-y divide-line">
                {e.actions.map((a) => (
                  <li key={a.id} className="space-y-1 px-5 py-3 text-sm">
                    <div className="flex items-center justify-between"><span>{humanize(a.action_type)}</span><StatusBadge status={a.state} /></div>
                    {a.error_message && <p className="text-xs text-rose-700">{a.error_message}</p>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
