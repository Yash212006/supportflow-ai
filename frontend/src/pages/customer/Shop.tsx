import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Minus, Plus, ShoppingCart } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Order, Product } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader, Skeleton } from '@/components/ui/misc';
import { money } from '@/lib/utils';
import { useAuth } from '@/stores/auth';

const EMOJI: Record<string, string> = { Appliances: '☕', Kitchen: '🍳', Lighting: '💡', Bedding: '🛏️', Decor: '🪴', Audio: '🎧', Electronics: '🔌', Furniture: '🪑', Bath: '🛁' };

export default function ShopPage() {
  const nav = useNavigate();
  const cur = useAuth((s) => s.user?.currency) ?? 'USD';
  const { data: products, isLoading } = useApi<Product[]>(['products'], '/api/customer/products');
  const [cart, setCart] = useState<Record<string, number>>({});
  const items = useMemo(() => (products ?? []).filter((p) => cart[p.id]).map((p) => ({ p, q: cart[p.id] })), [products, cart]);
  const total = items.reduce((s, { p, q }) => s + Number(p.price) * q, 0);
  const add = (id: string, d: number) => setCart((c) => {
    const q = Math.max(0, Math.min(20, (c[id] ?? 0) + d));
    const n = { ...c };
    if (q) n[id] = q; else delete n[id];
    return n;
  });
  const place = useAction(() => post<Order>('/api/customer/orders', { items: items.map(({ p, q }) => ({ product_id: p.id, quantity: q })) }), { invalidate: [['customer']] });
  return (
    <div>
      <PageHeader title="Shop" description="Northwind Living catalogue. Checkout uses PayPal Sandbox, so no real money moves." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {isLoading && [0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-44" />)}
          {products?.map((p) => (
            <Card key={p.id} className="flex flex-col">
              <div className="grid h-24 place-items-center rounded-t-xl bg-gradient-to-br from-slate-50 to-slate-100 text-4xl">{EMOJI[p.category] ?? '📦'}</div>
              <CardBody className="flex flex-1 flex-col">
                <p className="text-sm font-medium">{p.name}</p>
                <p className="text-xs text-muted">{p.category} · {p.refundable_days}-day returns</p>
                <div className="mt-auto flex items-center justify-between pt-3">
                  <span className="font-semibold tabular-nums">{money(p.price, cur)}</span>
                  {cart[p.id] ? (
                    <div className="flex items-center gap-1">
                      <Button size="icon" variant="secondary" className="h-7 w-7" onClick={() => add(p.id, -1)} aria-label="Remove one"><Minus className="h-3 w-3" /></Button>
                      <span className="w-6 text-center text-sm">{cart[p.id]}</span>
                      <Button size="icon" variant="secondary" className="h-7 w-7" onClick={() => add(p.id, 1)} aria-label="Add one"><Plus className="h-3 w-3" /></Button>
                    </div>
                  ) : (
                    <Button size="sm" variant="secondary" onClick={() => add(p.id, 1)}>Add</Button>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
        <Card className="h-fit lg:sticky lg:top-6">
          <CardHeader title={<span className="flex items-center gap-2"><ShoppingCart className="h-4 w-4" /> Cart</span>} />
          <CardBody className="space-y-3">
            {!items.length && <p className="text-sm text-muted">Your cart is empty.</p>}
            {items.map(({ p, q }) => (
              <div key={p.id} className="flex justify-between text-sm">
                <span>{q}× {p.name}</span>
                <span className="tabular-nums">{money(Number(p.price) * q, cur)}</span>
              </div>
            ))}
            <div className="flex justify-between border-t border-line pt-3 font-semibold">
              <span>Total</span>
              <span className="tabular-nums">{money(total, cur)}</span>
            </div>
            <Button className="w-full" disabled={!items.length} loading={place.isPending} onClick={async () => {
              const o = await place.mutateAsync(undefined);
              setCart({});
              nav(`/customer/orders/${o.id}`, { state: { justPlaced: true } });
            }}>
              Place order
            </Button>
            <p className="text-center text-xs text-muted">Prices are set by the store, not the browser. <Badge tone="indigo">PayPal Sandbox</Badge></p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
