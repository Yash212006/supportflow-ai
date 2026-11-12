import { ListPage } from '@/components/ListPage';
import type { Customer } from '@/lib/types';
import { money, humanize } from '@/lib/utils';
import { useAuth } from '@/stores/auth';

export default function Customers() {
  const cur = useAuth((s) => s.user?.currency) ?? 'USD';
  return (
    <ListPage<Customer>
      title="Customers"
      endpoint="/api/customers"
      searchable
      rowKey={(c) => c.id}
      rowLink={(c) => `/manager/customers/${c.id}`}
      columns={[
        { key: 'n', header: 'Name', cell: (c) => <div><p className="font-medium">{c.full_name}</p><p className="text-xs text-muted">{c.email}</p></div> },
        { key: 'c', header: 'City', cell: (c) => c.city },
        { key: 's', header: 'Segment', cell: (c) => humanize(c.segment) },
        { key: 'o', header: 'Orders', align: 'right', cell: (c) => c.orders },
        { key: 't', header: 'Open tickets', align: 'right', cell: (c) => c.open_tickets },
        { key: 'r', header: 'Refunds', align: 'right', cell: (c) => c.refunds },
        { key: 'sp', header: 'Spent', align: 'right', cell: (c) => money(c.spent, cur) },
      ]}
    />
  );
}
