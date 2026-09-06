"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api/client";

interface State<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Minimal data hook: runs `fetcher` whenever `deps` change, ignores stale
 * responses, exposes `reload`. Keeps pages free of fetch boilerplate.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[], options: { enabled?: boolean } = {}) {
  const enabled = options.enabled ?? true;
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: enabled });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    const id = ++latest.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    fetcher().then(
      (data) => {
        if (latest.current === id) setState({ data, error: null, loading: false });
      },
      (err) => {
        if (latest.current === id) setState((s) => ({ ...s, error: errorMessage(err), loading: false }));
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((updater: (prev: T | null) => T | null) => setState((s) => ({ ...s, data: updater(s.data) })), []);
  // A disabled hook reports empty rather than the last result it happened to
  // hold, derived here so no effect has to reset state.
  const view: State<T> = enabled ? state : { data: null, error: null, loading: false };
  return { ...view, reload, setData };
}

export function useDebounce<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
