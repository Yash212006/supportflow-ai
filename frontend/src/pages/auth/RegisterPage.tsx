import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Field, Input } from '@/components/ui/input';
import { Notice } from '@/components/ui/misc';
import { Logo } from '@/components/layout/AppShell';
import { errorMessage, post } from '@/lib/api';
import { homeFor, signIn } from '@/lib/session';

const schema = z.object({
  full_name: z.string().min(2, 'Enter your name'),
  email: z.email('Enter a valid email'),
  password: z.string().min(8, 'At least 8 characters'),
});
type Form = z.infer<typeof schema>;

export default function RegisterPage() {
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Form>({ resolver: zodResolver(schema) });
  const onSubmit = async (f: Form) => {
    setError(null);
    try {
      await post('/api/auth/register', f);
      const u = await signIn(f.email, f.password);
      nav(homeFor(u), { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <Logo />
        <h1 className="mt-8 text-2xl font-semibold tracking-tight">Create your account</h1>
        <p className="mt-1 text-sm text-muted">Shop at Northwind Living and get instant AI support.</p>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4">
          {error && <Notice tone="danger">{error}</Notice>}
          <Field label="Full name" error={formState.errors.full_name?.message}><Input {...register('full_name')} /></Field>
          <Field label="Email" error={formState.errors.email?.message}><Input type="email" {...register('email')} /></Field>
          <Field label="Password" error={formState.errors.password?.message}><Input type="password" {...register('password')} /></Field>
          <Button type="submit" className="w-full" size="lg" loading={formState.isSubmitting}>Create account</Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted">Already have an account? <Link to="/login" className="font-medium text-brand-600 hover:underline">Sign in</Link></p>
      </div>
    </div>
  );
}
