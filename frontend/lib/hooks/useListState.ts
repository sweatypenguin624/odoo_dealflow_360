"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

/** List page state (page, filters, search) kept in the URL so it survives reloads and back navigation. */
export function useListState(defaults: Record<string, string> = {}) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const state = useMemo(() => {
    const out: Record<string, string> = { ...defaults };
    params.forEach((v, k) => (out[k] = v));
    return out;
  }, [params, defaults]);

  const set = useCallback(
    (patch: Record<string, string | number | undefined | null>, resetPage = true) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === null || v === "") next.delete(k);
        else next.set(k, String(v));
      }
      if (resetPage && !("page" in patch)) next.delete("page");
      router.replace(`${pathname}?${next.toString()}`);
    },
    [params, router, pathname],
  );
  const page = Number(state.page ?? 1) || 1;
  return { state, set, page, setPage: (p: number) => set({ page: p }, false) };
}
