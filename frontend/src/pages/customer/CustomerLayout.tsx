import { Outlet } from 'react-router-dom';
import { CreditCard, LayoutDashboard, LifeBuoy, MessageSquareText, Package, ReceiptText, ShoppingBag } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';

export default function CustomerLayout() {
  return (
    <AppShell
      area="Customer portal"
      nav={[
        { items: [
          { to: '/customer', label: 'Home', icon: <LayoutDashboard />, end: true },
          { to: '/customer/chat', label: 'AI support chat', icon: <MessageSquareText /> },
        ] },
        { section: 'Shopping', items: [
          { to: '/customer/shop', label: 'Shop', icon: <ShoppingBag /> },
          { to: '/customer/orders', label: 'My orders', icon: <Package /> },
          { to: '/customer/payments', label: 'Payments', icon: <CreditCard /> },
        ] },
        { section: 'Help', items: [
          { to: '/customer/tickets', label: 'Support tickets', icon: <LifeBuoy /> },
          { to: '/customer/refunds', label: 'Refunds', icon: <ReceiptText /> },
        ] },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
