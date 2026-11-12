import { ListPage } from '@/components/ListPage';
import { useApi } from '@/lib/queries';
import type { Execution, Overview } from '@/lib/types';
import { Badge, StatusBadge, SampleBadge } from '@/components/ui/badge';
import { Stat } from '@/components/ui/misc';
import { ago, humanize, pct } from '@/lib/utils';

export default function AiOperations() {
  const { data: o } = useApi<Overview>(['overview', '30'], '/api/analytics/overview?days=30');
  return (
    <ListPage<Execution>
      title="AI operations"
      description="Every agent run with its steps, tool calls, policy decisions and outcome. Reasoning is summarised; raw model chain-of-thought is never stored."
      endpoint="/api/agents/executions"
      filters={[
        { param: 'workflow', label: 'Workflow', options: ['support', 'copilot', 'dashboard'] },
        { param: 'status', label: 'Status', options: ['RUNNING', 'COMPLETED', 'FAILED'] },
      ]}
      header={o && (
        <div className="mb-6 grid gap-4 sm:grid-cols-4">
          <Stat label="Agent runs (30d)" value={o.ai_executions} />
          <Stat label="Resolved autonomously" value={pct(o.ai_autonomous_rate)} tone="good" />
          <Stat label="Needed a human" value={pct(o.ai_human_rate)} tone="warn" />
          <Stat label="Escalation rate" value={pct(o.escalation_rate)} />
        </div>
      )}
      rowKey={(e) => e.id}
      rowLink={(e) => `/manager/ai-operations/${e.id}`}
      columns={[
        { key: 'w', header: 'Workflow', cell: (e) => <span className="flex items-center gap-1.5"><Badge tone="indigo">{e.workflow}</Badge><SampleBadge show={e.is_sample} /></span> },
        { key: 'i', header: 'Input', cell: (e) => <div className="max-w-sm"><p className="truncate">{e.input_summary}</p><p className="text-xs text-muted">{humanize(e.intent)}</p></div> },
        { key: 'o', header: 'Outcome', cell: (e) => <span className="flex flex-wrap gap-1">{e.resolved_autonomously && <Badge tone="green">Autonomous</Badge>}{e.required_human && <Badge tone="amber">Human needed</Badge>}{e.decision_outcome && <StatusBadge status={e.decision_outcome} />}</span> },
        { key: 'm', header: 'Mode', cell: (e) => <span className="text-xs text-muted">{e.llm_mode}</span> },
        { key: 's', header: 'Status', cell: (e) => <StatusBadge status={e.status} /> },
        { key: 't', header: 'Tools', align: 'right', cell: (e) => e.tool_count ?? 0 },
        { key: 'd', header: 'Duration', align: 'right', cell: (e) => (e.duration_ms != null ? `${e.duration_ms} ms` : '—') },
        { key: 'c', header: 'When', cell: (e) => <span className="text-xs text-muted">{ago(e.created_at)}</span> },
      ]}
    />
  );
}
