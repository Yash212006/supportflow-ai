import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Bot, ShieldCheck, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Field, Input } from '@/components/ui/input';
import { Notice } from '@/components/ui/misc';
import { Logo } from '@/components/layout/AppShell';
import { errorMessage } from '@/lib/api';
import { homeFor, signIn } from '@/lib/session';

const schema = z.object({ email: z.string().min(3, 'Enter your email'), password: z.string().min(1, 'Enter your password') });
type Form = z.infer<typeof schema>;

const DEMO = [
  { label: 'Customer', who: 'Priya Sharma', email: 'priya@customer.demo', password: 'Customer@123' },
  { label: 'Support manager', who: 'Maya Manager', email: 'manager@supportflow.demo', password: 'Demo@12345' },
  { label: 'Support agent', who: 'Sam Support', email: 'agent@supportflow.demo', password: 'Demo@12345' },
  { label: 'Admin', who: 'Asha Admin', email: 'admin@supportflow.demo', password: 'Demo@12345' },
];

export default function LoginPage() {
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, setValue, formState } = useForm<Form>({ resolver: zodResolver(schema) });
  const onSubmit = async (f: Form) => {
    setError(null);
    try {
      const u = await signIn(f.email, f.password);
      nav(homeFor(u), { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="flex flex-col justify-center px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <Logo />
          <h1 className="mt-8 text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-muted">Autonomous customer support and financial operations.</p>
          <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4">
            {error && <Notice tone="danger">{error}</Notice>}
            <Field label="Email" error={formState.errors.email?.message}>
              <Input type="email" autoComplete="email" {...register('email')} />
            </Field>
            <Field label="Password" error={formState.errors.password?.message}>
              <Input type="password" autoComplete="current-password" {...register('password')} />
            </Field>
            <Button type="submit" className="w-full" size="lg" loading={formState.isSubmitting}>
              Sign in
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted">
            New customer? <Link to="/register" className="font-medium text-brand-600 hover:underline">Create an account</Link>
          </p>
          <div className="mt-8 rounded-xl border border-dashed border-line p-4">
            <p className="text-xs font-medium text-slate-700">Demo accounts (seeded sample data)</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  data-demo={d.label}
                  onClick={() => {
                    setValue('email', d.email);
                    setValue('password', d.password);
                    void onSubmit({ email: d.email, password: d.password });
                  }}
                  className="rounded-lg border border-line bg-white px-3 py-2 text-left text-xs hover:border-brand-500 hover:bg-brand-50"
                >
                  <span className="block font-medium text-ink">{d.label}</span>
                  <span className="text-muted">{d.who}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-violet-700 lg:block">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.15),transparent_50%)]" />
        <div className="relative flex h-full flex-col justify-center px-16 text-white">
          <h2 className="max-w-md text-3xl font-semibold leading-tight">Support that resolves, not just responds.</h2>
          <p className="mt-4 max-w-md text-brand-100">AI agents investigate orders, apply your refund policy, and execute PayPal refunds, with every financial action governed, approved and audited.</p>
          <ul className="mt-10 space-y-5">
            {[
              [Bot, 'Six cooperating agents', 'Orchestrator, investigation, policy, risk, resolution and manager copilot.'],
              [ShieldCheck, 'Deterministic policy engine', 'The AI proposes; versioned business rules decide.'],
              [Wallet, 'Real PayPal Sandbox payments', 'Orders, captures and refunds via the APIMatic PayPal SDK.'],
            ].map(([Icon, t, d], i) => {
              const I = Icon as typeof Bot;
              return (
                <li key={i} className="flex gap-4">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/15"><I className="h-5 w-5" /></span>
                  <span>
                    <span className="block font-medium">{t as string}</span>
                    <span className="text-sm text-brand-100">{d as string}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
