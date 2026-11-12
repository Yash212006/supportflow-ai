import { useEffect, useRef, useState } from 'react';
import { Bot, ChevronDown, Plus, SendHorizonal, Sparkles, User, Wrench } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useApi, useAction } from '@/lib/queries';
import { errorMessage, get, post } from '@/lib/api';
import type { ActionCard } from '@/lib/types';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, StatusBadge } from '@/components/ui/badge';
import { ActionResultCard } from '@/components/ActionCard';
import { ago, cn, humanize, money } from '@/lib/utils';

interface ToolCard { tool: string; args: Record<string, unknown>; result: unknown }
interface Proposal { proposal: { order_id: string; order_number: number; amount: string; currency: string; reason: string }; predicted_outcome: string; explanation: string; policy_version: number | null; risk: { level: string; score: number } }
interface Turn { role: 'user' | 'assistant'; content: string; cards?: ToolCard[]; proposal?: Proposal | null; llm_mode?: string; at: string }

function Rich({ text }: { text: string }) {
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      {text.split('\n').map((line, i) => {
        const bullet = /^\s*[-•]\s+/.test(line);
        const html = line.replace(/^\s*[-•]\s+/, '').split(/(\*\*[^*]+\*\*)/g).map((p, j) => (p.startsWith('**') ? <strong key={j}>{p.slice(2, -2)}</strong> : <span key={j}>{p}</span>));
        return bullet ? <div key={i} className="flex gap-2"><span className="text-brand-500">•</span><span>{html}</span></div> : <p key={i}>{html}</p>;
      })}
    </div>
  );
}

function ResultView({ value }: { value: unknown }) {
  const rows = Array.isArray(value) ? value : value && typeof value === 'object' && Array.isArray((value as { items?: unknown[] }).items) ? (value as { items: unknown[] }).items : null;
  if (rows && rows.length && typeof rows[0] === 'object') {
    const cols = Object.keys(rows[0] as object).filter((k) => !k.endsWith('_id') && k !== 'id').slice(0, 6);
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-muted">{cols.map((c) => <th key={c} className="px-2 py-1 font-medium">{humanize(c)}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">
            {rows.slice(0, 12).map((r, i) => <tr key={i}>{cols.map((c) => <td key={c} className="px-2 py-1">{fmt((r as Record<string, unknown>)[c])}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
    );
  }
  return <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-[11px]">{JSON.stringify(value, null, 2)}</pre>;
}
const fmt = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v).slice(0, 60) : String(v));

function ToolCardView({ c }: { c: ToolCard }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-line bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs">
        <Wrench className="h-3.5 w-3.5 text-slate-400" /> <code className="font-medium">{c.tool}</code>
        <span className="truncate text-muted">{Object.entries(c.args ?? {}).map(([k, v]) => `${k}=${fmt(v)}`).join(', ')}</span>
        <ChevronDown className={cn('ml-auto h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>
      {open && <div className="border-t border-line p-2"><ResultView value={c.result} /></div>}
    </div>
  );
}

function ProposalCard({ p }: { p: Proposal }) {
  const [result, setResult] = useState<ActionCard | null>(null);
  const submit = useAction(() => post<ActionCard>('/api/refunds', { order_id: p.proposal.order_id, amount: Number(p.proposal.amount), reason: p.proposal.reason }), { invalidate: [['/api/refunds'], ['overview']] });
  return (
    <div className="rounded-lg border border-brand-200 bg-brand-50/50 p-3 text-sm">
      <p className="font-medium">Refund proposal · order #{p.proposal.order_number} · {money(p.proposal.amount, p.proposal.currency)}</p>
      <p className="mt-1 text-xs text-slate-600">Predicted: <StatusBadge status={p.predicted_outcome} /> under policy v{p.policy_version} · risk <StatusBadge status={p.risk?.level} /></p>
      <p className="mt-1 text-xs text-muted">Dry run only. Nothing has been executed.</p>
      {result ? <div className="mt-2"><ActionResultCard card={{ ...result, kind: 'refund' }} staff /></div> : (
        <Button size="sm" className="mt-2" loading={submit.isPending} onClick={async () => setResult(await submit.mutateAsync(undefined))}>Submit to execution engine</Button>
      )}
    </div>
  );
}

const STARTERS = ['Show pending approvals', 'What is our autonomy trend over the last 4 weeks?', 'Top complaints this month', 'Refund rate by product', 'Summarise failed agent executions', 'Prepare a refund proposal for order #1054'];

export default function Copilot() {
  const qc = useQueryClient();
  const [convId, setConvId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const { data: convs } = useApi<{ id: string; title: string; updated_at: string }[]>(['copilot-convs'], '/api/agents/copilot/conversations');
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns.length, busy]);

  const open = async (id: string) => {
    const c = await get<{ messages: { role: string; content: string; meta: { cards?: ToolCard[]; proposal?: Proposal; llm_mode?: string }; created_at: string }[] }>(`/api/agents/copilot/conversations/${id}`);
    setConvId(id);
    setTurns(c.messages.map((m) => ({ role: m.role === 'ASSISTANT' ? 'assistant' : 'user', content: m.content, cards: m.meta?.cards, proposal: m.meta?.proposal, llm_mode: m.meta?.llm_mode, at: m.created_at })));
  };
  const send = async (msg: string) => {
    if (!msg.trim() || busy) return;
    setTurns((t) => [...t, { role: 'user', content: msg, at: new Date().toISOString() }]);
    setText('');
    setBusy(true);
    try {
      const r = await post<{ conversation_id: string; answer: string; cards: ToolCard[]; proposal: Proposal | null; llm_mode: string }>('/api/agents/copilot/run', { message: msg, conversation_id: convId });
      setConvId(r.conversation_id);
      setTurns((t) => [...t, { role: 'assistant', content: r.answer, cards: r.cards, proposal: r.proposal, llm_mode: r.llm_mode, at: new Date().toISOString() }]);
      qc.invalidateQueries({ queryKey: ['copilot-convs'] });
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid h-[calc(100vh-7.5rem)] gap-4 lg:grid-cols-[260px_1fr]">
      <Card className="hidden flex-col overflow-hidden lg:flex">
        <div className="border-b border-line p-3"><Button variant="secondary" className="w-full" onClick={() => { setConvId(null); setTurns([]); }}><Plus className="h-4 w-4" /> New chat</Button></div>
        <div className="flex-1 overflow-y-auto">
          {convs?.map((c) => (
            <button key={c.id} onClick={() => void open(c.id)} className={cn('block w-full border-b border-line px-4 py-3 text-left hover:bg-slate-50', c.id === convId && 'bg-brand-50/60')}>
              <p className="truncate text-sm font-medium">{c.title}</p>
              <p className="text-xs text-muted">{ago(c.updated_at)}</p>
            </button>
          ))}
        </div>
      </Card>
      <Card className="flex min-h-0 flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-line px-5 py-3">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-violet-100 text-violet-700"><Sparkles className="h-4 w-4" /></span>
          <div><p className="text-sm font-semibold">Manager copilot</p><p className="text-xs text-muted">Read-only analysis tools. Refund proposals are dry runs until you submit them.</p></div>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto bg-slate-50/50 px-5 py-6">
          {!turns.length && (
            <div className="mx-auto max-w-lg py-8 text-center">
              <Bot className="mx-auto h-10 w-10 text-violet-500" />
              <p className="mt-3 font-medium">Ask about orders, refunds, tickets, policies or AI performance</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">{STARTERS.map((s) => <button key={s} onClick={() => void send(s)} className="rounded-full border border-line bg-white px-3 py-1.5 text-xs hover:border-violet-400">{s}</button>)}</div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className={cn('flex gap-3', t.role === 'user' && 'flex-row-reverse')}>
              <div className={cn('grid h-8 w-8 shrink-0 place-items-center rounded-full', t.role === 'user' ? 'bg-slate-200' : 'bg-violet-100 text-violet-700')}>{t.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}</div>
              <div className={cn('max-w-[85%] space-y-2', t.role === 'user' && 'text-right')}>
                <div className={cn('inline-block rounded-2xl px-4 py-2.5 text-left', t.role === 'user' ? 'rounded-tr-sm bg-violet-600 text-sm text-white' : 'rounded-tl-sm border border-line bg-white')}>{t.role === 'user' ? t.content : <Rich text={t.content} />}</div>
                {t.proposal && <ProposalCard p={t.proposal} />}
                {t.cards?.map((c, j) => <ToolCardView key={j} c={c} />)}
                {t.role === 'assistant' && t.llm_mode && <p className="text-[11px] text-muted"><Badge className="font-normal">{t.llm_mode}</Badge></p>}
              </div>
            </div>
          ))}
          {busy && <p className="text-xs text-muted">Copilot is querying…</p>}
          <div ref={endRef} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); void send(text); }} className="flex gap-2 border-t border-line bg-white p-3">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask the copilot…" className="h-10 flex-1 rounded-lg border border-line px-3 text-sm focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-100" />
          <Button type="submit" size="lg" loading={busy} disabled={!text.trim()} aria-label="Send"><SendHorizonal className="h-4 w-4" /></Button>
        </form>
      </Card>
    </div>
  );
}
