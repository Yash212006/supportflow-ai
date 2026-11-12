import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth, isManager, isStaff, type Role } from '@/stores/auth';
import { homeFor } from '@/lib/session';
import LoginPage from '@/pages/auth/LoginPage';
import RegisterPage from '@/pages/auth/RegisterPage';
import CustomerLayout from '@/pages/customer/CustomerLayout';
import ManagerLayout from '@/pages/manager/ManagerLayout';
import CustomerDashboard from '@/pages/customer/Dashboard';
import ShopPage from '@/pages/customer/Shop';
import CustomerOrders from '@/pages/customer/Orders';
import CustomerOrderDetail from '@/pages/customer/OrderDetail';
import CheckoutReturn from '@/pages/customer/CheckoutReturn';
import CustomerChat from '@/pages/customer/Chat';
import CustomerTickets from '@/pages/customer/Tickets';
import CustomerTicketDetail from '@/pages/customer/TicketDetail';
import CustomerRefunds from '@/pages/customer/Refunds';
import CustomerPayments from '@/pages/customer/Payments';
import Overview from '@/pages/manager/Overview';
import Approvals from '@/pages/manager/Approvals';
import ApprovalDetail from '@/pages/manager/ApprovalDetail';
import Tickets from '@/pages/manager/Tickets';
import TicketDetail from '@/pages/manager/TicketDetail';
import Orders from '@/pages/manager/Orders';
import OrderDetail from '@/pages/manager/OrderDetail';
import Customers from '@/pages/manager/Customers';
import CustomerDetail from '@/pages/manager/CustomerDetail';
import Payments from '@/pages/manager/Payments';
import PaymentDetail from '@/pages/manager/PaymentDetail';
import Refunds from '@/pages/manager/Refunds';
import AiOperations from '@/pages/manager/AiOperations';
import ExecutionDetail from '@/pages/manager/ExecutionDetail';
import Policies from '@/pages/manager/Policies';
import Knowledge from '@/pages/manager/Knowledge';
import Copilot from '@/pages/manager/Copilot';
import Risk from '@/pages/manager/Risk';
import AuditLogs from '@/pages/manager/AuditLogs';
import Settings from '@/pages/manager/Settings';

// AG Studio (AG Grid + AG Charts enterprise) is large: load it only on the analytics route.
const Analytics = lazy(() => import('@/pages/manager/Analytics'));

function Guard({ allow, children }: { allow: (r?: Role) => boolean; children: ReactNode }) {
  const { user, accessToken } = useAuth();
  if (!accessToken || !user) return <Navigate to="/login" replace />;
  if (!allow(user.role)) return <Navigate to={homeFor(user)} replace />;
  return <>{children}</>;
}

const Loading = () => (
  <div className="grid h-64 place-items-center text-muted">
    <Loader2 className="h-5 w-5 animate-spin" />
  </div>
);

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/" element={<Navigate to={homeFor(user)} replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/customer" element={<Guard allow={(r) => r === 'CUSTOMER'}><CustomerLayout /></Guard>}>
        <Route index element={<CustomerDashboard />} />
        <Route path="shop" element={<ShopPage />} />
        <Route path="orders" element={<CustomerOrders />} />
        <Route path="orders/:id" element={<CustomerOrderDetail />} />
        <Route path="checkout/return" element={<CheckoutReturn />} />
        <Route path="chat" element={<CustomerChat />} />
        <Route path="chat/:id" element={<CustomerChat />} />
        <Route path="tickets" element={<CustomerTickets />} />
        <Route path="tickets/:id" element={<CustomerTicketDetail />} />
        <Route path="refunds" element={<CustomerRefunds />} />
        <Route path="payments" element={<CustomerPayments />} />
      </Route>
      <Route path="/manager" element={<Guard allow={isStaff}><ManagerLayout /></Guard>}>
        <Route index element={<Overview />} />
        <Route path="approvals" element={<Guard allow={isManager}><Approvals /></Guard>} />
        <Route path="approvals/:id" element={<ApprovalDetail />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="tickets/:id" element={<TicketDetail />} />
        <Route path="orders" element={<Orders />} />
        <Route path="orders/:id" element={<OrderDetail />} />
        <Route path="customers" element={<Customers />} />
        <Route path="customers/:id" element={<CustomerDetail />} />
        <Route path="payments" element={<Payments />} />
        <Route path="payments/:id" element={<PaymentDetail />} />
        <Route path="refunds" element={<Refunds />} />
        <Route path="ai-operations" element={<AiOperations />} />
        <Route path="ai-operations/:id" element={<ExecutionDetail />} />
        <Route path="policies" element={<Policies />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="copilot" element={<Copilot />} />
        <Route path="risk" element={<Risk />} />
        <Route path="analytics" element={<Suspense fallback={<Loading />}><Analytics /></Suspense>} />
        <Route path="audit" element={<Guard allow={isManager}><AuditLogs /></Guard>} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
