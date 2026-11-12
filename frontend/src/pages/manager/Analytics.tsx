import { useCallback, useMemo, useRef, useState } from 'react';
import { AgStudio } from 'ag-studio-react';
import { AgStudioAiModule, AgStudioLicenseManager, AgStudioModuleRegistry, createAiHarness, type AgStudioApi } from 'ag-studio';
import { Eye, Pencil, RotateCcw, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '@/lib/queries';
import { del, errorMessage, get, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input, Select } from '@/components/ui/input';
import { Notice, PageHeader, Skeleton } from '@/components/ui/misc';
import { SupportFlowStudioAdapter } from '@/integrations/ag-studio/supportflowAdapter';
import { supportflowStudioTheme } from '@/integrations/ag-studio/theme';
import { DASHBOARD_PAGES, defaultReportState } from '@/integrations/ag-studio/dashboards';

const LICENSE = import.meta.env.VITE_AG_LICENSE_KEY as string | undefined;
if (LICENSE) AgStudioLicenseManager.setLicenseKey(LICENSE);
AgStudioModuleRegistry.registerModules([AgStudioAiModule]);

interface Source { id: string; name: string; data: Record<string, unknown>[] }
interface Saved { id: string; name: string; is_default: boolean; updated_at: string }
interface AiConfig { enabled: boolean; mode: string; models: { id: string; label: string }[] }

const adapter = new SupportFlowStudioAdapter();

export default function Analytics() {
  const qc = useQueryClient();
  const { data: ds, isLoading, error } = useApi<{ sources: Source[] }>(['datasets'], '/api/analytics/datasets');
  const { data: saved } = useApi<Saved[]>(['dashboards'], '/api/dashboards');
  const { data: ai } = useApi<AiConfig>(['studio-ai'], '/api/studio-ai/config');
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [state, setState] = useState<{ key: string; value: unknown }>({ key: 'default', value: defaultReportState() });
  const [name, setName] = useState('My SupportFlow dashboard');
  const apiRef = useRef<AgStudioApi | null>(null);

  const data = useMemo(() => (ds ? { sources: ds.sources.map((s) => ({ id: s.id, name: s.name, data: s.data })) } : undefined), [ds]);
  const aiSetup = useMemo(() => {
    if (!ai?.enabled) return undefined;
    return ({ api }: { api: AgStudioApi }) =>
      createAiHarness(api, {
        adapter,
        primary: 'lead',
        models: ai.models,
        promptStarters: [
          { label: 'Refund trend', prompt: 'Add a line chart of daily refunded amount and explain any spikes.' },
          { label: 'Autonomy by intent', prompt: 'Show which ticket intents the AI resolves autonomously vs needs a human.' },
          { label: 'Payment failures', prompt: 'Build a page analysing failed payments by category and month.' },
        ],
      });
  }, [ai?.enabled, ai?.models]);

  const load = useCallback(async (id: string) => {
    if (id === 'default') return setState({ key: `default-${Date.now()}`, value: defaultReportState() });
    try {
      const d = await get<{ id: string; name: string; state: unknown }>(`/api/dashboards/${id}`);
      setName(d.name);
      setState({ key: d.id + Date.now(), value: d.state });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  type ReportState = { pages?: { id: string }[]; selectedPageId?: string };
  const current = state.value as ReportState;
  const pageTabs = (current.pages ?? []).map((pg) => ({ id: pg.id, label: DASHBOARD_PAGES.find((d) => d.id === pg.id)?.label ?? pg.id }));
  const showPage = (id: string) => {
    const live = (apiRef.current?.getState() as ReportState | undefined) ?? current;
    setState({ key: `${id}-${Date.now()}`, value: { ...live, selectedPageId: id } });
  };

  const save = async () => {
    const api = apiRef.current;
    if (!api) return;
    try {
      await post('/api/dashboards', { name, state: api.getState(), is_default: true, studio_version: '3.1.0' });
      qc.invalidateQueries({ queryKey: ['dashboards'] });
      toast.success('Dashboard saved');
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  if (error) return <Notice tone="danger" title="Couldn't load analytics data">{errorMessage(error)}</Notice>;
  return (
    <div className="flex h-[calc(100vh-7.5rem)] flex-col">
      <PageHeader
        title={<span className="flex items-center gap-2">Analytics <Badge tone="indigo">AG Studio</Badge></span>}
        description="Financial, support, AI operations and risk dashboards over live tenant data. Rows carry a data_origin column (sample, live, paypal_sandbox)."
        actions={
          <>
            <Select className="w-56" defaultValue="default" onChange={(e) => void load(e.target.value)}>
              <option value="default">SupportFlow defaults</option>
              {saved?.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_default ? ' (default)' : ''}</option>)}
            </Select>
            <Button variant="secondary" onClick={() => setMode(mode === 'view' ? 'edit' : 'view')}>{mode === 'view' ? <><Pencil className="h-4 w-4" /> Edit</> : <><Eye className="h-4 w-4" /> View</>}</Button>
          </>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {mode === 'view' && pageTabs.length > 1 && (
          <div className="inline-flex rounded-lg border border-line bg-white p-1" role="tablist" aria-label="Dashboard pages">
            {pageTabs.map((t) => (
              <button key={t.id} role="tab" aria-selected={current.selectedPageId === t.id} onClick={() => showPage(t.id)}
                className={`rounded-md px-3 py-1 text-sm ${current.selectedPageId === t.id ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>
                {t.label}
              </button>
            ))}
          </div>
        )}
        {mode === 'edit' && (
          <>
            <Input className="w-64" value={name} onChange={(e) => setName(e.target.value)} />
            <Button size="sm" onClick={() => void save()}><Save className="h-4 w-4" /> Save</Button>
            <Button size="sm" variant="ghost" onClick={() => void load('default')}><RotateCcw className="h-4 w-4" /> Reset to defaults</Button>
            {saved?.find((s) => s.name === name) && <Button size="sm" variant="ghost" onClick={async () => { const s = saved.find((x) => x.name === name)!; await del(`/api/dashboards/${s.id}`); qc.invalidateQueries({ queryKey: ['dashboards'] }); toast.success('Deleted'); }}><Trash2 className="h-4 w-4" /> Delete saved</Button>}
          </>
        )}
        <span className="ml-auto flex items-center gap-2 text-xs text-muted">
          {!LICENSE && <Badge tone="amber">No AG Studio licence key: evaluation watermark</Badge>}
          {ai && (ai.enabled ? <Badge tone="green">AI assistant via backend ({ai.mode})</Badge> : <Badge>AI assistant off: no LLM key on backend</Badge>)}
        </span>
      </div>
      <div className="min-h-[600px] flex-1 overflow-hidden rounded-xl border border-line bg-white">
        {isLoading || !data ? <Skeleton className="h-full w-full" /> : (
          <AgStudio
            key={state.key}
            data={data}
            mode={mode}
            theme={supportflowStudioTheme}
            initialState={state.value as never}
            ai={aiSetup as never}
            onApiReady={(e) => { apiRef.current = e.api as AgStudioApi; }}
            onErrorRaised={(e) => console.warn('[AG Studio]', e)}
            style={{ height: '100%', width: '100%' }}
          />
        )}
      </div>
    </div>
  );
}
