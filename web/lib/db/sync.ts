import { ApiError, api } from '@/lib/api/client';
import {
  META_KEYS,
  type OutboxEntry,
  type SyncOutcome,
  backoffMs,
  db,
  getMeta,
  pending,
  recordFailure,
  resolve,
  setMeta,
  writeBundle,
} from './dexie';

/**
 * The sync protocol.
 *
 * On app open and on the `online` event, request /bundle/offline with the stored
 * ETag. A 304 costs one small round trip and nothing is written. A 200 is written
 * in a single Dexie transaction and meta.lastSyncAt advances.
 *
 * Conflict resolution for queued edits is last-write-wins on `updatedAt`, which is
 * the right rule for single-user preference data: the newest thing the user did is
 * what they meant.
 */

export const OUTBOX_TAG = 'gp-outbox';

export async function syncBundle(): Promise<SyncOutcome> {
  const etag = await getMeta<string>(META_KEYS.bundleEtag);

  try {
    // A 304 arrives as a thrown-free empty body; the client returns undefined.
    const response = await fetch('/api/bundle/offline', {
      headers: etag ? { 'If-None-Match': etag } : undefined,
      credentials: 'include',
    });

    if (response.status === 304) {
      return { status: 'unchanged' };
    }
    if (!response.ok) {
      return { status: 'failed', error: `HTTP ${response.status}` };
    }

    const bundle = await response.json();
    await writeBundle(bundle);

    const nextEtag = response.headers.get('ETag');
    if (nextEtag) await setMeta(META_KEYS.bundleEtag, nextEtag);

    return { status: 'updated', generatedAt: bundle.generatedAt };
  } catch (error) {
    return {
      status: 'failed',
      error: error instanceof Error ? error.message : 'sync failed',
    };
  }
}

/** How old the data on this device is. Drives the offline banner. */
export async function dataAge(): Promise<string | null> {
  const generated = await getMeta<string>(META_KEYS.generatedAt);
  const synced = await getMeta<string>(META_KEYS.lastSyncAt);
  return generated ?? synced ?? null;
}

async function replay(entry: OutboxEntry): Promise<void> {
  if (entry.kind === 'watchlist') {
    const payload = entry.payload as {
      archetypeIds: string[];
      minSeverity: string;
    };
    await api.updateWatchlist(payload.archetypeIds, payload.minSeverity);
    return;
  }
  if (entry.kind === 'holdings') {
    await api.updateHoldings(entry.payload as { symbol: string; weight: number }[]);
    return;
  }
  throw new Error(`unknown outbox kind: ${entry.kind}`);
}

export interface FlushResult {
  flushed: number;
  failed: number;
  remaining: number;
}

/**
 * Replay queued mutations.
 *
 * A 4xx other than 401 means the server rejected the edit on its merits — a
 * malformed symbol, a weight over 100%. Retrying it forever would wedge the
 * outbox behind an entry that can never succeed, so it is dropped.
 */
export async function flushOutbox(): Promise<FlushResult> {
  const entries = await pending();
  let flushed = 0;
  let failed = 0;

  for (const entry of entries) {
    if (entry.id === undefined) continue;

    const waitFor = backoffMs(entry.attempts);
    const since = Date.now() - new Date(entry.updatedAt).getTime();
    if (entry.attempts > 0 && since < waitFor) continue;

    try {
      await replay(entry);
      await resolve(entry.id);
      flushed += 1;
    } catch (error) {
      const permanent =
        error instanceof ApiError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 401 &&
        error.status !== 429;

      if (permanent) {
        await resolve(entry.id);
        failed += 1;
      } else {
        await recordFailure(
          entry.id,
          error instanceof Error ? error.message : 'replay failed',
        );
        failed += 1;
      }
    }
  }

  return { flushed, failed, remaining: (await pending()).length };
}

/**
 * Ask the service worker to flush when connectivity returns.
 *
 * iOS has no Background Sync, so registration failing is expected there rather
 * than exceptional — the flush happens on next foreground instead.
 */
export async function requestBackgroundSync(): Promise<boolean> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
    return false;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    const sync = (registration as ServiceWorkerRegistration & {
      sync?: { register: (tag: string) => Promise<void> };
    }).sync;
    if (!sync) return false;
    await sync.register(OUTBOX_TAG);
    return true;
  } catch {
    return false;
  }
}

/** Wire the whole protocol up. Returns a teardown function. */
export function startSync(): () => void {
  const onOnline = () => {
    void syncBundle();
    void flushOutbox();
  };

  void syncBundle();
  void flushOutbox();

  if (typeof window !== 'undefined') {
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }
  return () => undefined;
}

export async function clearLocalData(): Promise<void> {
  const database = db();
  await database.delete();
  await database.open();
}
