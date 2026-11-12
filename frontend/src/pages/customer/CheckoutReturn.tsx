import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { post, errorMessage } from '@/lib/api';
import type { Payment } from '@/lib/types';
import { Card, CardBody } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/badge';
import { KeyValue } from '@/components/ui/misc';
import { money } from '@/lib/utils';

export default function CheckoutReturn() {
  const [sp] = useSearchParams();
  const paymentId = sp.get('payment');
  const cancelled = sp.get('cancelled') === '1';
  const [payment, setPayment] = useState<Payment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!paymentId || cancelled || started.current) return;
    started.current = true;
    post<Payment>(`/api/customer/payments/${paymentId}/capture`).then(setPayment).catch((e) => setError(errorMessage(e)));
  }, [paymentId, cancelled]);

  const captured = payment?.status === 'CAPTURED';
  return (
    <div className="mx-auto max-w-lg py-10">
      <Card>
        <CardBody className="py-8 text-center">
          {cancelled ? (
            <>
              <XCircle className="mx-auto h-10 w-10 text-slate-400" />
              <h1 className="mt-3 text-lg font-semibold">Payment cancelled</h1>
              <p className="mt-1 text-sm text-muted">You cancelled on PayPal. Nothing was charged.</p>
            </>
          ) : error ? (
            <>
              <XCircle className="mx-auto h-10 w-10 text-rose-500" />
              <h1 className="mt-3 text-lg font-semibold">Payment not completed</h1>
              <p className="mt-1 text-sm text-muted">{error}</p>
              <p className="mt-2 text-xs text-muted">If PayPal's answer was unclear, we'll confirm the final status automatically. You won't be charged twice.</p>
            </>
          ) : !payment ? (
            <>
              <Loader2 className="mx-auto h-10 w-10 animate-spin text-brand-600" />
              <h1 className="mt-3 text-lg font-semibold">Confirming with PayPal…</h1>
              <p className="mt-1 text-sm text-muted">Capturing your approved payment.</p>
            </>
          ) : (
            <>
              {captured ? <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" /> : <Loader2 className="mx-auto h-10 w-10 text-amber-500" />}
              <h1 className="mt-3 text-lg font-semibold">{captured ? 'Payment captured' : 'Payment is being processed'}</h1>
              <p className="mt-1 text-sm text-muted">{captured ? 'PayPal confirmed the capture.' : 'PayPal has not completed the capture yet. We will update the order when it does.'}</p>
              <div className="mt-6 rounded-lg bg-slate-50 p-4 text-left">
                <KeyValue items={[["Status", <StatusBadge status={payment.status} />], ["Amount", money(payment.amount, payment.currency)], ["PayPal order", payment.paypal_order_id], ["Capture ID", payment.paypal_capture_id], ["Payer", payment.payer_email]]} />
              </div>
            </>
          )}
          <div className="mt-6 flex justify-center gap-2">
            {payment && <Link to={`/customer/orders/${payment.order_id}`}><Button>View order</Button></Link>}
            <Link to="/customer/orders"><Button variant="secondary">My orders</Button></Link>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
