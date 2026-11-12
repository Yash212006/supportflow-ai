import { Outlet } from 'react-router-dom';
import { Activity, BarChart3, BookOpenText, Bot, ClipboardCheck, CreditCard, FileClock, Gauge, LifeBuoy, Package, ReceiptText, Scale, Settings, ShieldAlert, Users } from 'lucide-react';
import { AppShell, type NavItem } from '@/components/layout/AppShell';
import { useApi } from '@/lib/queries';
import { useAuth, isManager } from '@/stores/auth';
import type { Overview } from '@/lib/types';

export default function ManagerLayout() {
  const role = useAuth((s) => s.user?.role);
  const mgr = isManager(role);
  const { data } = useApi<Overview>(['overview', 30], '/api/analytics/overview?days=30', { refetchInterval: 30000 });
  const ops: NavItem[] = [
    { to: '/manager', label: 'Overview', icon: <Gauge />, end: true },
    ...(mgr ? [{ to: '/manager/approvals', label: 'Approvals', icon: <ClipboardCheck />, badge: data?.pending_approvals }] : []),
    { to: '/manager/tickets', label: 'Tickets', icon: <LifeBuoy /> },
    { to: '/manager/copilot', label: 'Manager copilot', icon: <Bot /> },
  ];
  return (
    <AppShell
      area={mgr ? 'Manager workspace' : 'Agent workspace'}
      nav={[
        { items: ops },
        { section: 'Commerce', items: [
          { to: '/manager/orders', label: 'Orders', icon: <Package /> },
          { to: '/manager/customers', label: 'Customers', icon: <Users /> },
          { to: '/manager/payments', label: 'Payments', icon: <CreditCard /> },
          { to: '/manager/refunds', label: 'Refunds', icon: <ReceiptText /> },
        ] },
        { section: 'Intelligence', items: [
          { to: '/manager/analytics', label: 'Analytics (AG Studio)', icon: <BarChart3 /> },
          { to: '/manager/ai-operations', label: 'AI operations', icon: <Activity /> },
          { to: '/manager/risk', label: 'Risk monitor', icon: <ShieldAlert /> },
        ] },
        { section: 'Governance', items: [
          { to: '/manager/policies', label: 'Policies', icon: <Scale /> },
          { to: '/manager/knowledge', label: 'Knowledge base', icon: <BookOpenText /> },
          ...(mgr ? [{ to: '/manager/audit', label: 'Audit log', icon: <FileClock /> }] : []),
          { to: '/manager/settings', label: 'Integrations', icon: <Settings /> },
        ] },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
