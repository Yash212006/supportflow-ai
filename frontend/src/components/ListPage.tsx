import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { useApi } from '@/lib/queries';
import type { Page } from '@/lib/types';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { DataTable, type Column } from '@/components/ui/table';
import { ErrorState, PageHeader, Skeleton } from '@/components/ui/misc';
import { humanize } from '@/lib/utils';

export interface Filter { param: string; label: string; options: string[] }

export function ListPage<T>({ title, description, endpoint, columns, rowKey, rowLink, filters = [], searchable, actions, pageSize = 25, refetchInterval, header, fixedParams }: {
  title: string; description?: ReactNode; endpoint: string; columns: Column<T>[]; rowKey: (r: T) => string; rowLink?: (r: T) => string;
  filters?: Filter[]; searchable?: boolean; actions?: ReactNode; pageSize?: number; refetchInterval?: number; header?: ReactNode; fixedParams?: Record<string, string>;
}) {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [vals, setVals] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
  if (query) params.set('q', query);
  Object.entries(fixedParams ?? {}).forEach(([k, v]) => params.set(k, v));
  Object.entries(vals).forEach(([k, v]) => v && params.set(k, v));
  const url = `${endpoint}?${params}`;
  const { data, isLoading, error, refetch } = useApi<Page<T>>([endpoint, url], url, { refetchInterval });
  return (
    <div>
      <PageHeader title={title} description={description} actions={actions} />
      {header}
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          {searchable && (
            <form onSubmit={(e) => { e.preventDefault(); setOffset(0); setQuery(q.trim()); }} className="relative w-full max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" className="pl-8" />
            </form>
          )}
          {filters.map((f) => (
            <Select key={f.param} value={vals[f.param] ?? ''} onChange={(e) => { setOffset(0); setVals({ ...vals, [f.param]: e.target.value }); }} className="w-auto min-w-40">
              <option value="">{f.label}: all</option>
              {f.options.map((o) => <option key={o} value={o}>{humanize(o)}</option>)}
            </Select>
          ))}
          <span className="ml-auto text-xs text-muted">{data ? `${data.total} total` : ''}</span>
        </div>
        {error ? <div className="p-4"><ErrorState error={error} retry={refetch} /></div> : isLoading ? <div className="space-y-2 p-4">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-9" />)}</div> : (
          <DataTable rows={data?.items ?? []} columns={columns} rowKey={rowKey} onRowClick={rowLink ? (r) => nav(rowLink(r)) : undefined} />
        )}
        {data && data.total > pageSize && (
          <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-2.5 text-xs text-muted">
            {offset + 1}–{Math.min(offset + pageSize, data.total)} of {data.total}
            <Button size="icon" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))} aria-label="Previous"><ChevronLeft className="h-4 w-4" /></Button>
            <Button size="icon" variant="ghost" disabled={offset + pageSize >= data.total} onClick={() => setOffset(offset + pageSize)} aria-label="Next"><ChevronRight className="h-4 w-4" /></Button>
          </div>
        )}
      </Card>
    </div>
  );
}
