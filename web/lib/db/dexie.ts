import Dexie, { type Table } from 'dexie';

import type {
  AnalogEvent,
  ArchetypeDetail,
  Channel,
  Digest,
  Holding,
  OfflineBundle,
} from '@/lib/api/client';

/**
 * The offline store.
 *
 * Every screen reads from here first and paints immediately, then reconciles
 * with the network. That ordering is the whole point: on a warm launch there is
 * never a loading spinner, because there is always something to show.
 */

export interface StoredAnalogSummary {
  archetypeId: string;
  target: string;
  window: string;
  asOf: string;
  sampleSize: number;
  meanCarBps: number;
  medianCarBps: number;
  stdevBps: number;
  hitRate: number;
  p5Bps: number;
  p95Bps: number;
  tStat: number;
  pValue: number;
  analogs: AnalogEvent[];
}

export interface StoredEvent {
  eventId: string;
  archetypeId: string;
  eventDate: string;
  headline: string;
  sources: string[];
  matchScore: number;
}

export interface StoredDigest {
  digestDate: string;
  payload: Digest;
}

export interface MetaRow {
  key: string;
  value: unknown;
}

/** A mutation made offline, waiting to be replayed. */
export interface OutboxEntry {
  id?: number;
  kind: 'watchlist' | 'holdings';
  payload: unknown;
  createdAt: string;
  /** Last-write-wins is resolved on this, not on arrival order at the server. */
  updatedAt: string;
  attempts: number;
  lastError?: string;
}

export const META_KEYS = {
  lastSyncAt: 'lastSyncAt',
  bundleEtag: 'bundleEtag',
  schemaVersion: 'schemaVersion',
  generatedAt: 'generatedAt',
  analogDetailOmitted: 'analogDetailOmitted',
} as const;

export class ImpactoDB extends Dexie {
  archetypes!: Table<ArchetypeDetail, string>;
  channels!: Table<Channel, string>;
  analogSummaries!: Table<StoredAnalogSummary, [string, string, string]>;
  digests!: Table<StoredDigest, string>;
  events!: Table<StoredEvent, string>;
  holdings!: Table<Holding, string>;
  meta!: Table<MetaRow, string>;
  outbox!: Table<OutboxEntry, number>;

  constructor(name = 'impacto') {
    super(name);
    this.version(1).stores({
      archetypes: 'id, family',
      channels: 'id',
      analogSummaries: '[archetypeId+target+window], archetypeId, asOf',
      digests: 'digestDate',
      events: 'eventId, eventDate, archetypeId',
      // Local mirror only; the server is the source of truth for holdings.
      holdings: 'symbol',
      meta: 'key',
      outbox: '++id, kind, createdAt',
    });
  }
}

let instance: ImpactoDB | null = null;

export function db(): ImpactoDB {
  if (!instance) instance = new ImpactoDB();
  return instance;
}

/** Test seam: point the app at a named database, or reset between tests. */
export function setDb(next: ImpactoDB | null): void {
  instance = next;
}

// ------------------------------------------------------------------- meta
export async function getMeta<T>(key: string): Promise<T | undefined> {
  const row = await db().meta.get(key);
  return row?.value as T | undefined;
}

export async function setMeta(key: string, value: unknown): Promise<void> {
  await db().meta.put({ key, value });
}

// ------------------------------------------------------------------- sync
export interface SyncOutcome {
  status: 'updated' | 'unchanged' | 'failed';
  generatedAt?: string;
  error?: string;
}

/**
 * Write a bundle into IndexedDB in one transaction.
 *
 * Single transaction on purpose: a partial write would leave the app showing
 * archetypes from today next to statistics from last week, with no way to tell.
 */
export async function writeBundle(bundle: OfflineBundle): Promise<void> {
  const database = db();
  await database.transaction(
    'rw',
    [
      database.archetypes,
      database.channels,
      database.analogSummaries,
      database.digests,
      database.events,
      database.meta,
    ],
    async () => {
      await Promise.all([
        database.archetypes.bulkPut(bundle.archetypes),
        database.channels.bulkPut(bundle.channels),
        database.analogSummaries.bulkPut(bundle.analogSummaries),
        database.events.bulkPut(bundle.recentEvents),
      ]);
      if (bundle.digest) {
        await database.digests.put({
          digestDate: bundle.digest.digest_date,
          payload: bundle.digest,
        });
      }
      await database.meta.bulkPut([
        { key: META_KEYS.lastSyncAt, value: new Date().toISOString() },
        { key: META_KEYS.generatedAt, value: bundle.generatedAt },
        { key: META_KEYS.schemaVersion, value: 1 },
        {
          key: META_KEYS.analogDetailOmitted,
          value: bundle.analogDetailOmitted,
        },
      ]);
    },
  );
}

// ----------------------------------------------------------------- outbox
export async function enqueue(
  kind: OutboxEntry['kind'],
  payload: unknown,
): Promise<number> {
  const now = new Date().toISOString();
  // One pending entry per kind. A user who toggles their watchlist five times
  // offline wants the final state replayed, not five conflicting writes.
  const existing = await db().outbox.where('kind').equals(kind).first();
  if (existing?.id !== undefined) {
    await db().outbox.update(existing.id, {
      payload,
      updatedAt: now,
      attempts: 0,
      lastError: undefined,
    });
    return existing.id;
  }
  return db().outbox.add({
    kind,
    payload,
    createdAt: now,
    updatedAt: now,
    attempts: 0,
  });
}

export async function pending(): Promise<OutboxEntry[]> {
  return db().outbox.orderBy('createdAt').toArray();
}

export async function resolve(id: number): Promise<void> {
  await db().outbox.delete(id);
}

/**
 * Note a failed replay.
 *
 * `countsAsAttempt: false` records what went wrong without consuming a retry.
 * That is the right treatment for a request that never reached the server: it
 * tells us nothing about whether the edit is acceptable, and counting it would
 * push a perfectly good edit down an exponential wait for the sole reason that
 * the user was somewhere with no signal.
 */
export async function recordFailure(
  id: number,
  error: string,
  { countsAsAttempt = true }: { countsAsAttempt?: boolean } = {},
): Promise<void> {
  const entry = await db().outbox.get(id);
  if (!entry) return;
  await db().outbox.update(id, {
    attempts: countsAsAttempt ? entry.attempts + 1 : entry.attempts,
    lastError: error,
  });
}

/** Exponential backoff, capped so a long outage does not push retries to hours. */
export function backoffMs(attempts: number): number {
  return Math.min(2 ** attempts * 1000, 5 * 60 * 1000);
}
