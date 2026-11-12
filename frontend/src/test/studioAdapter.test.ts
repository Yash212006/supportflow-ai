import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AgLlmRequest } from 'ag-studio';
import { SupportFlowStudioAdapter } from '@/integrations/ag-studio/supportflowAdapter';
import { useAuth } from '@/stores/auth';

const req = { input: [{ type: 'message', role: 'user', content: [{ type: 'text', text: 'add a chart' }] }], tools: [] } as unknown as AgLlmRequest;

async function collect(stream: AsyncIterable<{ type: string }>) {
  const out: string[] = [];
  for await (const e of stream) out.push(e.type);
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe('SupportFlowStudioAdapter', () => {
  it('sends the bearer token to the backend proxy, never a model key', async () => {
    useAuth.setState({ accessToken: 'jwt-123' } as never);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'r1', createdAt: 1, status: 'completed', output: [] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await new SupportFlowStudioAdapter('/api/studio-ai/turn').executeTurn(req).complete;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/studio-ai/turn');
    expect(init.headers.Authorization).toBe('Bearer jwt-123');
    expect(JSON.stringify(init)).not.toMatch(/sk-|api[_-]?key/i);
  });

  it('replays text and tool calls as AG-UI events', async () => {
    const body = {
      id: 'r2', createdAt: 1, status: 'completed',
      output: [
        { id: 'm1', type: 'message', role: 'assistant', content: [{ type: 'text', text: 'Done' }] },
        { id: 'f1', type: 'function_call', callId: 'c1', name: 'add_widget', arguments: '{}' },
      ],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })));
    const turn = new SupportFlowStudioAdapter('/x').executeTurn(req);
    expect(await collect(turn.stream as AsyncIterable<{ type: string }>)).toEqual([
      'TEXT_MESSAGE_START', 'TEXT_MESSAGE_CONTENT', 'TEXT_MESSAGE_END', 'TOOL_CALL_START', 'TOOL_CALL_ARGS', 'TOOL_CALL_END',
    ]);
  });

  it('reports a backend error as a failed turn instead of inventing output', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'llm_not_configured', message: 'No LLM provider is configured.' } }), { status: 503 })));
    const res = await new SupportFlowStudioAdapter('/x').executeTurn(req).complete;
    expect(res.status).toBe('failed');
    expect(res.output).toEqual([]);
    expect(res.error?.code).toBe('llm_not_configured');
  });

  it('reports a network failure as failed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const res = await new SupportFlowStudioAdapter('/x').executeTurn(req).complete;
    expect(res.status).toBe('failed');
    expect(res.error?.code).toBe('network_error');
  });
});
