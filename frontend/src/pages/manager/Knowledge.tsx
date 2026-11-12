import { useRef, useState } from 'react';
import { BookOpen, Search, Trash2, Upload } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { api, del, post } from '@/lib/api';
import type { Citation, KnowledgeDoc } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, StatusBadge } from '@/components/ui/badge';
import { Field, Input, Select } from '@/components/ui/input';
import { DataTable } from '@/components/ui/table';
import { Modal, Notice, PageHeader } from '@/components/ui/misc';
import { useAuth, isManager } from '@/stores/auth';
import { dateTime, humanize } from '@/lib/utils';

const CATS = ['refund_policy', 'shipping', 'product', 'procedures', 'faq', 'business_policy', 'payments'];

export default function Knowledge() {
  const role = useAuth((s) => s.user?.role);
  const { data: docs } = useApi<KnowledgeDoc[]>(['kb'], '/api/knowledge/documents');
  const { data: status } = useApi<{ embeddings: { model: string; semantic: boolean } }>(['integrations'], '/api/integrations/status');
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: '', category: 'faq', doc_key: '' });
  const fileRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Citation[] | null>(null);
  const upload = useAction(async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) throw new Error('Choose a file');
    const fd = new FormData();
    fd.append('file', file);
    fd.append('title', f.title || file.name);
    fd.append('category', f.category);
    if (f.doc_key) fd.append('doc_key', f.doc_key);
    return api('/api/knowledge/upload', { method: 'POST', body: fd });
  }, { invalidate: [['kb']], success: 'Document ingested' });
  const remove = useAction((id: string) => del(`/api/knowledge/documents/${id}`), { invalidate: [['kb']], success: 'Removed' });
  const search = useAction(() => post<Citation[]>('/api/knowledge/search', { query: q }));
  return (
    <div>
      <PageHeader title="Knowledge base" description="Policies, procedures and FAQs the agents cite. Uploading a document with an existing key creates a new version and retires the old one." actions={isManager(role) && <Button onClick={() => setOpen(true)}><Upload className="h-4 w-4" /> Upload</Button>} />
      {status && !status.embeddings.semantic && <Notice tone="info" className="mb-6" title={`Embeddings: ${status.embeddings.model}`}>No embedding provider key is configured, so retrieval uses a local lexical hashing embedding (keyword-based, not semantic). Add an OpenAI or Gemini key and re-embed for semantic search.</Notice>}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader title="Documents" />
          <DataTable rows={docs ?? []} rowKey={(d) => d.id} columns={[
            { key: 't', header: 'Title', cell: (d) => <div><p className="font-medium">{d.title}</p><p className="text-xs text-muted">{d.filename} · {d.chunk_count} chunks</p></div> },
            { key: 'c', header: 'Category', cell: (d) => <Badge>{humanize(d.category)}</Badge> },
            { key: 'v', header: 'Version', cell: (d) => <span className="text-xs">v{d.version} {d.is_current ? <Badge tone="green">current</Badge> : <Badge>superseded</Badge>}</span> },
            { key: 's', header: 'Status', cell: (d) => <StatusBadge status={d.status} /> },
            { key: 'd', header: 'Added', cell: (d) => <span className="text-xs">{dateTime(d.created_at)}</span> },
            { key: 'x', header: '', cell: (d) => isManager(role) && <Button size="icon" variant="ghost" onClick={() => remove.mutate(d.id)} aria-label="Delete"><Trash2 className="h-4 w-4" /></Button> },
          ]} />
        </Card>
        <Card className="h-fit">
          <CardHeader title="Test retrieval" description="What the policy intelligence agent would cite" />
          <CardBody className="space-y-3">
            <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 1) void search.mutateAsync(undefined).then(setHits); }} className="flex gap-2">
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. refund window for blenders" />
              <Button type="submit" size="icon" loading={search.isPending} aria-label="Search"><Search className="h-4 w-4" /></Button>
            </form>
            {hits?.length === 0 && <p className="text-sm text-muted">No matches.</p>}
            {hits?.map((h, i) => (
              <div key={i} className="rounded-lg border border-line p-3">
                <p className="flex items-center gap-1.5 text-xs font-medium"><BookOpen className="h-3.5 w-3.5" /> {h.title} v{h.version} <span className="ml-auto text-muted">{h.score.toFixed(3)}</span></p>
                <p className="mt-1 line-clamp-4 text-xs text-slate-600">{h.excerpt ?? (h as unknown as { content: string }).content}</p>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Upload document" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={upload.isPending} onClick={async () => { await upload.mutateAsync(undefined); setOpen(false); }}>Upload & index</Button></>}>
        <div className="space-y-4">
          <Field label="File" hint="PDF, TXT, DOCX or Markdown"><input ref={fileRef} type="file" accept=".pdf,.txt,.docx,.md" className="block w-full text-sm" /></Field>
          <Field label="Title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Category"><Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATS.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</Select></Field>
          <Field label="Document key (optional)" hint="Reuse an existing key, e.g. refund-policy, to publish a new version"><Input value={f.doc_key} onChange={(e) => setF({ ...f, doc_key: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}
