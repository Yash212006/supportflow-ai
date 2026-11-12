/**
 * AgLlmAdapter for the AG Studio Agent Framework.
 *
 * AG Studio ships no LLM. Its harness calls `executeTurn(request)`; this adapter forwards the
 * AgLlmRequest to SupportFlow's backend (`POST /api/studio-ai/turn`), which holds the model
 * credentials, enforces staff-only access and rejects any financial tool. The browser never sees a key.
 *
 * The backend answers with a complete AgLlmResponse; we replay it as AG-UI stream events so the
 * chat panel renders text and tool calls exactly as it would for a streaming provider.
 */
import type { AgAiEvent, AgLlmAdapter, AgLlmExecuteTurnOptions, AgLlmRequest, AgLlmResponse } from 'ag-studio';
import { useAuth } from '@/stores/auth';

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '';

export class SupportFlowStudioAdapter implements AgLlmAdapter {
  constructor(private readonly endpoint = `${BASE}/api/studio-ai/turn`) {}

  executeTurn(request: AgLlmRequest, options?: AgLlmExecuteTurnOptions) {
    const complete = this.call(request, options);
    const stream = {
      async *[Symbol.asyncIterator](): AsyncIterator<AgAiEvent> {
        const res = await complete;
        for (const item of res.output) {
          if (item.type === 'message') {
            const text = item.content.map((c) => ('text' in c ? c.text : 'refusal' in c ? c.refusal : '')).join('');
            yield { type: 'TEXT_MESSAGE_START', messageId: item.id, role: 'assistant' } as AgAiEvent;
            if (text) yield { type: 'TEXT_MESSAGE_CONTENT', messageId: item.id, delta: text } as AgAiEvent;
            yield { type: 'TEXT_MESSAGE_END', messageId: item.id } as AgAiEvent;
          } else if (item.type === 'function_call') {
            yield { type: 'TOOL_CALL_START', toolCallId: item.callId, toolCallName: item.name } as AgAiEvent;
            yield { type: 'TOOL_CALL_ARGS', toolCallId: item.callId, delta: item.arguments } as AgAiEvent;
            yield { type: 'TOOL_CALL_END', toolCallId: item.callId } as AgAiEvent;
          }
        }
      },
    };
    return { stream, complete };
  }

  private async call(request: AgLlmRequest, options?: AgLlmExecuteTurnOptions): Promise<AgLlmResponse> {
    const token = useAuth.getState().accessToken;
    try {
      const r = await fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ ...request, trace: options?.trace }),
        signal: options?.signal,
      });
      const body = await r.json().catch(() => null);
      if (!r.ok) {
        const message = body?.error?.message ?? `AI request failed (${r.status})`;
        return failed(body?.error?.code ?? `http_${r.status}`, message);
      }
      return body as AgLlmResponse;
    } catch (e) {
      if ((e as Error).name === 'AbortError') return { id: 'cancelled', createdAt: Date.now(), status: 'cancelled', output: [] };
      return failed('network_error', (e as Error).message);
    }
  }
}

function failed(code: string, message: string): AgLlmResponse {
  return { id: `err_${Date.now()}`, createdAt: Date.now(), status: 'failed', output: [], error: { code, message } };
}
