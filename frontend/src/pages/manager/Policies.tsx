import { useEffect, useMemo, useState } from 'react';
import { FlaskConical, Plus, Save, Trash2 } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post, put, ApiError } from '@/lib/api';
import type { Decision, Order, Page, Policy, PolicyRule } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, StatusBadge } from '@/components/ui/badge';
import { Input, Select } from '@/components/ui/input';
import { Notice, PageHeader, Skeleton } from '@/components/ui/misc';
import { DecisionTrace } from '@/components/DecisionTrace';
import { useAuth, isManager } from '@/stores/auth';
import { cn, dateOnly, humanize } from '@/lib/utils';

interface PolicyResp { items: Policy[]; facts: Record<string, string>; operators: string[]; outcomes: string[] }
interface EvalResp { outcome: string; matched_rule_id: string | null; explanation: string; evaluated: Decision['evaluated_conditions']; facts: Record<string, unknown>; policy_version: number | null; missing_facts: string[] }

function parseValue(op: string, raw: string): unknown {
  if (op === 'is_true' || op === 'is_false') return undefined;
  if (op === 'between') return raw.split(',').map((s) => Number(s.trim()));
  if (op === 'in' || op === 'not_in') return raw.split(',').map((s) => s.trim()).filter(Boolean);
  const n = Number(raw);
  return raw.trim() !== '' && !Number.isNaN(n) ? n : raw;
}
const showValue = (v: unknown) => (v === undefined || v === null ? '' : Array.isArray(v) ? v.join(', ') : String(v));

export default function Policies() {
  const role = useAuth((s) => s.user?.role);
  const canEdit = isManager(role);
  const { data, isLoading, refetch } = useApi<PolicyResp>(['policies'], '/api/policies');
  const { data: orders } = useApi<Page<Order>>(['orders-for-dryrun'], '/api/orders?limit=100');
  const [sel, setSel] = useState<string | null>(null);
  const policy = data?.items.find((p) => p.id === sel) ?? data?.items.find((p) => p.key === 'refund_policy') ?? data?.items[0];
  const active = policy?.versions.find((v) => v.version === policy.active_version) ?? policy?.versions[0];
  const [rules, setRules] = useState<PolicyRule[]>([]);
  const [defaultOutcome, setDefaultOutcome] = useState('REQUIRES_APPROVAL');
  const [note, setNote] = useState('');
  const [problems, setProblems] = useState<string[]>([]);
  const [dry, setDry] = useState({ order_id: '', amount: '' });
  const [evalRes, setEvalRes] = useState<EvalResp | null>(null);

  useEffect(() => {
    if (active) {
      setRules(JSON.parse(JSON.stringify(active.rules)));
      setDefaultOutcome(active.default_outcome);
      setEvalRes(null);
      setProblems([]);
    }
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = useMemo(() => JSON.stringify(rules) !== JSON.stringify(active?.rules ?? []) || defaultOutcome !== active?.default_outcome, [rules, defaultOutcome, active]);
  const save = useAction(() => put(`/api/policies/${policy?.id}`, { rules, default_outcome: defaultOutcome, change_note: note || 'Updated rules' }), { invalidate: [['policies']], success: 'Saved as a new policy version' });
  const runDry = useAction(() => post<EvalResp>('/api/policies/evaluate', { action_type: policy?.action_type, order_id: dry.order_id || null, amount: dry.amount ? Number(dry.amount) : null, rules: dirty ? rules : null, default_outcome: defaultOutcome }));

  const upd = (i: number, r: Partial<PolicyRule>) => setRules(rules.map((x, j) => (j === i ? { ...x, ...r } : x)));
  const updCond = (i: number, k: number, c: Partial<PolicyRule['conditions'][number]>) => upd(i, { conditions: rules[i].conditions.map((x, j) => (j === k ? { ...x, ...c } : x)) });

  if (isLoading || !data || !policy) return <Skeleton className="h-96" />;
  const factKeys = Object.keys(data.facts);
  return (
    <div>
      <PageHeader title="Policy engine" description="Deterministic, versioned business rules. The AI can propose actions but never bypass these decisions. Rules run in priority order; the first match wins." />
      <div className="mb-6 flex flex-wrap gap-2">
        {data.items.map((p) => (
          <button key={p.id} onClick={() => setSel(p.id)} className={cn('rounded-lg border px-4 py-2 text-left text-sm', p.id === policy.id ? 'border-brand-500 bg-brand-50' : 'border-line bg-white hover:border-slate-300')}>
            <span className="block font-medium">{p.name}</span>
            <span className="text-xs text-muted">{humanize(p.action_type)} · v{p.active_version}</span>
          </button>
        ))}
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title={`${policy.name} — rules`} description={policy.description ?? undefined} action={canEdit && (
              <div className="flex items-center gap-2">
                {dirty && <Badge tone="amber">Unsaved draft</Badge>}
                <Button size="sm" variant="secondary" onClick={() => setRules([...rules, { id: `rule-${rules.length + 1}`, name: 'New rule', priority: (rules.at(-1)?.priority ?? 0) + 10, match: 'all', conditions: [{ field: 'refund_amount', op: 'lt', value: 0 }], outcome: 'REQUIRES_APPROVAL', explanation: '' }])}><Plus className="h-3.5 w-3.5" /> Rule</Button>
              </div>
            )} />
            <div className="divide-y divide-line">
              {rules.map((r, i) => (
                <div key={i} className="space-y-3 px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Input className="h-8 w-16 text-xs" type="number" value={r.priority} disabled={!canEdit} onChange={(e) => upd(i, { priority: Number(e.target.value) })} title="Priority" />
                    <Input className="h-8 w-44 font-mono text-xs" value={r.id} disabled={!canEdit} onChange={(e) => upd(i, { id: e.target.value })} title="Rule ID" />
                    <Input className="h-8 min-w-48 flex-1 text-sm font-medium" value={r.name ?? ''} disabled={!canEdit} onChange={(e) => upd(i, { name: e.target.value })} />
                    <Select className="h-8 w-36 text-xs" value={r.match ?? 'all'} disabled={!canEdit} onChange={(e) => upd(i, { match: e.target.value as 'all' | 'any' })}><option value="all">match all</option><option value="any">match any</option></Select>
                    <span className="text-xs text-muted">→</span>
                    <Select className="h-8 w-52 text-xs" value={r.outcome} disabled={!canEdit} onChange={(e) => upd(i, { outcome: e.target.value })}>{data.outcomes.map((o) => <option key={o} value={o}>{humanize(o)}</option>)}</Select>
                    {canEdit && <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setRules(rules.filter((_, j) => j !== i))} aria-label="Delete rule"><Trash2 className="h-4 w-4" /></Button>}
                  </div>
                  <div className="space-y-1.5 pl-2">
                    {r.conditions.map((c, k) => (
                      <div key={k} className="flex flex-wrap items-center gap-2">
                        <span className="w-8 text-right text-[11px] uppercase text-muted">{k === 0 ? 'if' : r.match === 'any' ? 'or' : 'and'}</span>
                        <Select className="h-8 w-56 font-mono text-xs" value={c.field} disabled={!canEdit} onChange={(e) => updCond(i, k, { field: e.target.value })} title={data.facts[c.field]}>
                          {!factKeys.includes(c.field) && <option value={c.field}>{c.field}</option>}
                          {factKeys.map((f) => <option key={f} value={f}>{f}</option>)}
                        </Select>
                        <Select className="h-8 w-32 text-xs" value={c.op} disabled={!canEdit} onChange={(e) => updCond(i, k, { op: e.target.value, value: ['is_true', 'is_false'].includes(e.target.value) ? undefined : c.value })}>{data.operators.map((o) => <option key={o} value={o}>{o.replace('_', ' ')}</option>)}</Select>
                        {!['is_true', 'is_false'].includes(c.op) && <Input className="h-8 w-40 font-mono text-xs" defaultValue={showValue(c.value)} key={`${i}-${k}-${showValue(c.value)}`} disabled={!canEdit} onBlur={(e) => updCond(i, k, { value: parseValue(c.op, e.target.value) })} placeholder={c.op === 'between' ? 'min, max' : 'value'} />}
                        {canEdit && r.conditions.length > 1 && <button className="text-xs text-muted hover:text-rose-600" onClick={() => upd(i, { conditions: r.conditions.filter((_, j) => j !== k) })}>remove</button>}
                      </div>
                    ))}
                    {canEdit && <button className="ml-10 text-xs font-medium text-brand-600 hover:underline" onClick={() => upd(i, { conditions: [...r.conditions, { field: 'refund_amount', op: 'gt', value: 0 }] })}>+ condition</button>}
                  </div>
                  <Input className="h-8 text-xs" value={r.explanation ?? ''} disabled={!canEdit} onChange={(e) => upd(i, { explanation: e.target.value })} placeholder="Explanation shown to staff and customers" />
                </div>
              ))}
              <div className="flex flex-wrap items-center gap-3 bg-slate-50/60 px-5 py-3 text-sm">
                <span className="text-muted">If no rule matches:</span>
                <Select className="h-8 w-56 text-xs" value={defaultOutcome} disabled={!canEdit} onChange={(e) => setDefaultOutcome(e.target.value)}>{data.outcomes.map((o) => <option key={o} value={o}>{humanize(o)}</option>)}</Select>
              </div>
            </div>
            {canEdit && (
              <div className="space-y-3 border-t border-line px-5 py-4">
                {!!problems.length && <Notice tone="danger" title="Rules are invalid"><ul className="list-disc pl-4">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul></Notice>}
                <div className="flex flex-wrap items-center gap-2">
                  <Input className="max-w-md flex-1" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Change note (e.g. Raise auto-refund limit to 1500)" />
                  <Button disabled={!dirty} loading={save.isPending} onClick={async () => {
                    setProblems([]);
                    try { await save.mutateAsync(undefined); setNote(''); await refetch(); } catch (e) { if (e instanceof ApiError && Array.isArray(e.details)) setProblems(e.details as string[]); }
                  }}><Save className="h-4 w-4" /> Save as v{(policy.current_version ?? 0) + 1}</Button>
                  {dirty && <Button variant="ghost" onClick={() => { setRules(JSON.parse(JSON.stringify(active?.rules ?? []))); setDefaultOutcome(active?.default_outcome ?? 'REQUIRES_APPROVAL'); }}>Discard</Button>}
                </div>
              </div>
            )}
          </Card>
          <Card>
            <CardHeader title="Version history" description="Past decisions keep pointing at the version that made them" />
            <ul className="divide-y divide-line">
              {policy.versions.map((v) => (
                <li key={v.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                  <span className="font-mono font-medium">v{v.version}</span>
                  <StatusBadge status={(v as unknown as { status?: string }).status ?? (v.version === policy.active_version ? 'ACTIVE' : 'RETIRED')} />
                  <span className="flex-1 text-muted">{v.change_note}</span>
                  <span className="text-xs text-muted">{dateOnly(v.effective_from)} – {v.effective_to ? dateOnly(v.effective_to) : 'now'}</span>
                  <span className="text-xs text-muted">{v.rules.length} rules</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <Card className="h-fit xl:sticky xl:top-6">
          <CardHeader title={<span className="flex items-center gap-2"><FlaskConical className="h-4 w-4" /> Dry run</span>} description={dirty ? 'Testing your unsaved draft' : `Testing active v${policy.active_version}`} />
          <CardBody className="space-y-3">
            <Select value={dry.order_id} onChange={(e) => setDry({ ...dry, order_id: e.target.value })}>
              <option value="">Choose an order…</option>
              {orders?.items.filter((o) => o.payment_status).map((o) => <option key={o.id} value={o.id}>#{o.order_number} · {o.customer_name} · {o.total_amount} {o.is_sample ? '(sample)' : ''}</option>)}
            </Select>
            <Input type="number" step="0.01" value={dry.amount} onChange={(e) => setDry({ ...dry, amount: e.target.value })} placeholder="Refund amount (empty = full)" />
            <Button className="w-full" variant="secondary" disabled={!dry.order_id} loading={runDry.isPending} onClick={async () => setEvalRes(await runDry.mutateAsync(undefined))}>Evaluate (nothing is executed)</Button>
            {evalRes && (
              <div className="border-t border-line pt-3">
                <DecisionTrace decision={{ id: 'dry', policy_id: null, policy_version: evalRes.policy_version, action_type: policy.action_type, outcome: evalRes.outcome, matched_rule_id: evalRes.matched_rule_id, inputs: evalRes.facts, evaluated_conditions: evalRes.evaluated, explanation: evalRes.explanation, created_at: '' }} />
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
