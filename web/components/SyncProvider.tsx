'use client';
// 'use client': registers the service worker and drives the sync loop.

import { useEffect } from 'react';

import { startSync } from '@/lib/db/sync';

/**
 * Starts the sync protocol on mount and on every `online` event, and registers
 * the service worker.
 *
 * Deliberately renders nothing and holds no state: sync must not be able to
 * block or re-render the tree it wraps, or a slow network would cost a repaint
 * on every reconnect.
 */
export function SyncProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
      void navigator.serviceWorker.register('/sw.js').catch(() => {
        // A failed registration costs offline support, not the app.
      });
    }
    return startSync();
  }, []);

  return <>{children}</>;
}

export default SyncProvider;
