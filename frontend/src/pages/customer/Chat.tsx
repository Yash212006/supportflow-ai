import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { BookOpen, Bot, Plus, SendHorizonal, Ticket as TicketIcon, User } from 'lucide-react';
import { useApi } from '@/lib/queries';
import { errorMessage, post } from '@/lib/api';
import type { ChatMessage, Refund } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ActionResultCard } from '@/components/ActionCard';
import { ago, cn, humanize } from '@/lib/utils';
import { toast } from 'sonner';

interface Conv { id: string; title: string; ticket_id: string | null; updated_at: string }

export function MessageBubble({ m, refunds }: { m: ChatMessage; refunds?: Map<string, Refund> }) {
  const mine = m.role === 'CUSTOMER' || m.role === 'USER';
  const human = m.role === 'AGENT' || m.role === 'STAFF';
  return (
    <div className={cn('flex gap-3', mine && 'flex-row-reverse')}>
      <div className={cn('grid h-8 w-8 shrink-0 place-items-center rounded-full', mine ? 'bg-slate-200 text-slate-700' : human ? 'bg-emerald-100 text-emerald-700' : 'bg-brand-100 text-brand-700')}>
        {mine ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className={cn('max-w-[80%] space-y-2', mine && 'items-end text-right')}>
        <div className={cn('inline-block whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-left text-sm leading-relaxed', mine ? 'rounded-tr-sm bg-brand-600 text-white' : 'rounded-tl-sm border border-line bg-white text-ink')}>
          {human && <span className="mb-1 block text-xs font-medium text-emerald-700">Support team</span>}
          {m.content}
        </div>
        {!mine && m.meta?.actions?.map((a, i) => (
          <ActionResultCard key={i} card={a} liveStatus={a.refund_id ? refunds?.get(a.refund_id)?.status : undefined} />
        ))}
        {!mine && !!m.meta?.citations?.length && (
          <div className="flex flex-wrap gap-1.5">
            {m.meta.citations.map((c, i) => (
              <span key={i} title={c.excerpt} className="inline-flex items-center gap-1 rounded-md border border-line bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600">
                <BookOpen className="h-3 w-3" /> {c.title} v{c.version}
              </span>
            ))}
          </div>
        )}
        <p className="text-[11px] text-muted">
          {ago(m.created_at)}
          {!mine && m.meta?.ticket && <> · ticket #{m.meta.ticket.ticket_number}</>}
        </p>
      </div>
    </div>
  );
}

export default function CustomerChat() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  const [text, setText] = useState((loc.state as { prefill?: string } | null)?.prefill ?? '');
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const { data: convs } = useApi<Conv[]>(['customer', 'conversations'], '/api/customer/conversations');
  const { data: conv } = useApi<Conv & { messages: ChatMessage[] }>(['customer', 'conversation', id], id ? `/api/customer/conversations/${id}` : null);
  const { data: refunds } = useApi<Refund[]>(['customer', 'refunds'], '/api/customer/refunds', { refetchInterval: 15000 });
  const refundMap = useMemo(() => new Map((refunds ?? []).map((r) => [r.id, r])), [refunds]);
  const messages = id ? conv?.messages ?? [] : [];

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages.length, pending]);

  const send = async () => {
    const msg = text.trim();
    if (!msg || sending) return;
    setSending(true);
    setPending(msg);
    setText('');
    try {
      const r = await post<{ conversation_id: string; reply: ChatMessage }>('/api/customer/chat', { message: msg, conversation_id: id ?? null });
      await qc.invalidateQueries({ queryKey: ['customer'] });
      if (r.conversation_id !== id) nav(`/customer/chat/${r.conversation_id}`, { replace: !!id });
    } catch (e) {
      toast.error(errorMessage(e));
      setText(msg);
    } finally {
      setSending(false);
      setPending(null);
    }
  };

  return (
    <div className="grid h-[calc(100vh-7.5rem)] gap-4 lg:grid-cols-[260px_1fr]">
      <Card className="hidden flex-col overflow-hidden lg:flex">
        <div className="border-b border-line p-3">
          <Button className="w-full" variant="secondary" onClick={() => nav('/customer/chat')}><Plus className="h-4 w-4" /> New conversation</Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {convs?.map((c) => (
            <Link key={c.id} to={`/customer/chat/${c.id}`} className={cn('block border-b border-line px-4 py-3 hover:bg-slate-50', c.id === id && 'bg-brand-50/60')}>
              <p className="truncate text-sm font-medium">{c.title}</p>
              <p className="text-xs text-muted">{ago(c.updated_at)}</p>
            </Link>
          ))}
        </div>
      </Card>
      <Card className="flex min-h-0 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-100 text-brand-700"><Bot className="h-4 w-4" /></span>
            <div>
              <p className="text-sm font-semibold">SupportFlow assistant</p>
              <p className="text-xs text-muted">Checks your real orders and our refund policy</p>
            </div>
          </div>
          {conv?.ticket_id && <Link to={`/customer/tickets/${conv.ticket_id}`}><Badge tone="indigo"><TicketIcon className="h-3 w-3" /> View ticket</Badge></Link>}
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto bg-slate-50/50 px-5 py-6">
          {!id && !pending && (
            <div className="mx-auto max-w-md py-10 text-center">
              <Bot className="mx-auto h-10 w-10 text-brand-500" />
              <p className="mt-3 font-medium">How can we help?</p>
              <p className="mt-1 text-sm text-muted">Ask about an order, a delivery, a payment or a refund. Mention the order number if you have it.</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {['Where is my latest order?', 'I want a refund for my last order', 'Cancel my unpaid order', 'Talk to a human'].map((q) => (
                  <button key={q} onClick={() => setText(q)} className="rounded-full border border-line bg-white px-3 py-1.5 text-xs hover:border-brand-500">{q}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => <MessageBubble key={m.id} m={m} refunds={refundMap} />)}
          {pending && (
            <>
              <MessageBubble m={{ id: 'p', role: 'CUSTOMER', content: pending, created_at: new Date().toISOString() }} />
              <div className="flex items-center gap-2 text-xs text-muted"><span className="flex gap-1"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:120ms]" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:240ms]" /></span> Agents are investigating…</div>
            </>
          )}
          <div ref={endRef} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); void send(); }} className="flex gap-2 border-t border-line bg-white p-3">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your message…" maxLength={4000} className="h-10 flex-1 rounded-lg border border-line px-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100" />
          <Button type="submit" size="lg" loading={sending} disabled={!text.trim()} aria-label="Send"><SendHorizonal className="h-4 w-4" /></Button>
        </form>
        {conv && messages.length > 0 && <p className="bg-white px-4 pb-2 text-center text-[11px] text-muted">Answers use {humanize(messages[messages.length - 1]?.meta?.llm_mode ?? 'deterministic')} mode. Financial outcomes are decided by policy and PayPal, not by the assistant.</p>}
      </Card>
    </div>
  );
}
