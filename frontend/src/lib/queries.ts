import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import { errorMessage, get, post } from './api';

export function useApi<T>(key: QueryKey, path: string | null, opts: { refetchInterval?: number; enabled?: boolean } = {}) {
  return useQuery<T>({ queryKey: key, queryFn: () => get<T>(path as string), enabled: path !== null && (opts.enabled ?? true), refetchInterval: opts.refetchInterval });
}

export function useAction<TIn = unknown, TOut = unknown>(fn: (v: TIn) => Promise<TOut>, { invalidate = [], success }: { invalidate?: QueryKey[]; success?: string | ((r: TOut) => string | null) } = {}) {
  const qc = useQueryClient();
  return useMutation<TOut, Error, TIn>({
    mutationFn: fn,
    onSuccess: (r) => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      const m = typeof success === 'function' ? success(r) : success;
      if (m) toast.success(m);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export const postTo = <T,>(path: string) => (body?: unknown) => post<T>(path, body);
