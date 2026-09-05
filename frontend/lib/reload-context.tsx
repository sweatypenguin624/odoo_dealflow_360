"use client";

import { createContext, ReactNode, useCallback, useContext, useState } from "react";

// Every workspace screen fetches its own data client-side (this is an
// internal CRUD-heavy tool with lots of mutations, not a content site),
// so router.refresh() alone wouldn't re-trigger those fetches. Instead,
// "Reload Data" bumps a shared nonce that every screen includes in its
// data-fetching effect's dependency array.
interface ReloadContextValue {
  reloadNonce: number;
  reload: () => void;
}

const ReloadContext = createContext<ReloadContextValue | null>(null);

export function ReloadProvider({ children }: { children: ReactNode }) {
  const [reloadNonce, setReloadNonce] = useState(0);
  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);

  return <ReloadContext.Provider value={{ reloadNonce, reload }}>{children}</ReloadContext.Provider>;
}

export function useReload(): ReloadContextValue {
  const ctx = useContext(ReloadContext);
  if (!ctx) {
    throw new Error("useReload must be used within a ReloadProvider (the workspace layout)");
  }
  return ctx;
}
