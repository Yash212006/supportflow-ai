import { useState, type ReactNode } from 'react';
import { NavLink, Link, useNavigate } from 'react-router-dom';
import { Bell, LogOut, Menu, Sparkles, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/stores/auth';
import { useApi } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Notification } from '@/lib/types';
import { ago, cn, humanize } from '@/lib/utils';

export interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean; badge?: number }

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-violet-600 text-white shadow-sm">
        <Sparkles className="h-4 w-4" />
      </span>
      {!compact && (
        <span className="leading-tight">
          <span className="block text-sm font-semibold text-ink">SupportFlow AI</span>
        </span>
      )}
    </Link>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data } = useApi<{ items: Notification[]; unread: number }>(['notifications'], '/api/notifications', { refetchInterval: 20000 });
  const markAll = async () => {
    await post('/api/notifications/read-all');
    qc.invalidateQueries({ queryKey: ['notifications'] });
  };
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100" aria-label="Notifications">
        <Bell className="h-5 w-5" />
        {!!data?.unread && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">{data.unread}</span>}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-40 mt-2 w-80 overflow-hidden rounded-xl border border-line bg-white shadow-lg">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <span className="text-sm font-semibold">Notifications</span>
              <button onClick={markAll} className="text-xs text-brand-600 hover:underline">Mark all read</button>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {!data?.items.length && <p className="px-4 py-8 text-center text-sm text-muted">You're all caught up.</p>}
              {data?.items.map((n) => (
                <button
                  key={n.id}
                  onClick={async () => {
                    setOpen(false);
                    if (!n.read_at) await post(`/api/notifications/${n.id}/read`).catch(() => null);
                    qc.invalidateQueries({ queryKey: ['notifications'] });
                    if (n.link) nav(n.link);
                  }}
                  className={cn('block w-full border-b border-line px-4 py-3 text-left last:border-0 hover:bg-slate-50', !n.read_at && 'bg-brand-50/40')}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium uppercase tracking-wide text-muted">{humanize(n.type)}</span>
                    <span className="text-[11px] text-muted">{ago(n.created_at)}</span>
                  </div>
                  <p className="mt-0.5 text-sm font-medium text-ink">{n.title}</p>
                  {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{n.body}</p>}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function AppShell({ nav, children, area }: { nav: { section?: string; items: NavItem[] }[]; children: ReactNode; area: string }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [mobile, setMobile] = useState(false);
  const signOut = () => {
    logout();
    qc.clear();
    navigate('/login');
  };
  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center justify-between px-5">
        <Logo />
        <button className="lg:hidden" onClick={() => setMobile(false)} aria-label="Close menu">
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="px-5 pb-2 text-[11px] font-medium uppercase tracking-wider text-muted">{area}</div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {nav.map((g, i) => (
          <div key={i}>
            {g.section && <p className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">{g.section}</p>}
            <div className="space-y-0.5">
              {g.items.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.end}
                  onClick={() => setMobile(false)}
                  className={({ isActive }) => cn('flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors', isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100 hover:text-ink')}
                >
                  <span className="[&>svg]:h-4 [&>svg]:w-4">{n.icon}</span>
                  <span className="flex-1">{n.label}</span>
                  {!!n.badge && <span className="rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-800">{n.badge}</span>}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-line p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <div className="grid h-8 w-8 place-items-center rounded-full bg-slate-200 text-xs font-semibold text-slate-700">{user?.full_name?.split(' ').map((s) => s[0]).join('').slice(0, 2)}</div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{user?.full_name}</p>
            <p className="truncate text-xs text-muted">{humanize(user?.role)}</p>
          </div>
          <button onClick={signOut} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Sign out" title="Sign out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-line bg-white lg:block">{sidebar}</aside>
      {mobile && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setMobile(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-xl">{sidebar}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line bg-white/80 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <button className="lg:hidden" onClick={() => setMobile(true)} aria-label="Open menu">
              <Menu className="h-5 w-5" />
            </button>
            <span className="hidden text-sm text-muted sm:inline">{user?.business_name ?? 'Northwind Living'}</span>
          </div>
          <Notifications />
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
