'use client';
// 'use client': registers the service worker and drives the sync loop.

import { useEffect } from 'react';

/**
 * Starts the sync protocol on mount and on every `online` event, and registers
 * the service worker.
 *
 * The sync module is imported dynamically rather than statically. This component
 * sits in the root layout, so a static import would pull Dexie (~30 KB gzip)
 * into the first-load bundle of every route — including the statically generated
 * archetype pages, which never touch IndexedDB during their first paint. Loading
 * it after hydration keeps it off the critical path on a slow connection.
 *
 * Deliberately renders nothing and holds no state: sync must not be able to
 * block or re-render the tree it wraps.
 */
export function SyncProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
      void navigator.serviceWorker.register('/sw.js').catch(() => {
        // A failed registration costs offline support, not the app.
      });
    }

    let teardown: (() => void) | undefined;
    let cancelled = false;

    void import('@/lib/db/sync').then(({ startSync, flushOutbox }) => {
      if (cancelled) return;
      teardown = startSync();

      // The service worker asks the page to replay the outbox, because the
      // queue lives in the page's Dexie instance.
      navigator.serviceWorker?.addEventListener('message', (event) => {
        if ((event.data as { type?: string })?.type === 'flush-outbox') {
          void flushOutbox();
        }
      });
    });

    return () => {
      cancelled = true;
      teardown?.();
    };
  }, []);

  return <>{children}</>;
}

export default SyncProvider;
