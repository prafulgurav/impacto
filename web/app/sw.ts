/// <reference lib="webworker" />
import { defaultCache } from '@serwist/next/worker';
import type { PrecacheEntry, SerwistGlobalConfig } from 'serwist';
import {
  CacheFirst,
  ExpirationPlugin,
  NetworkFirst,
  NetworkOnly,
  Serwist,
  StaleWhileRevalidate,
} from 'serwist';

/**
 * The service worker.
 *
 * The caching strategy table below is the whole PWA design in one place. Two
 * entries are load-bearing for compliance rather than performance:
 *
 *   /api/explain/*  NetworkOnly — a stale explanation attached to today's market
 *                   move is the exact misleading output the compliance layer
 *                   exists to prevent. Caching one would be a compliance
 *                   failure, not a performance win.
 *   /api/me/*       NetworkOnly — never cache auth or PII, anywhere.
 */

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

const OUTBOX_TAG = 'gp-outbox';
const OFFLINE_URL = '/offline';

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    // --- never cached ----------------------------------------------------
    {
      matcher: ({ url }) =>
        url.pathname.startsWith('/api/explain') ||
        url.pathname.startsWith('/api/me') ||
        url.pathname.startsWith('/api/auth') ||
        url.pathname.startsWith('/api/push'),
      handler: new NetworkOnly(),
    },

    // --- the transmission map changes on deploy, not hourly ---------------
    {
      matcher: ({ url }) => url.pathname.startsWith('/api/knowledge'),
      handler: new StaleWhileRevalidate({
        cacheName: 'impacto-knowledge',
        plugins: [
          new ExpirationPlugin({ maxEntries: 64, maxAgeSeconds: 7 * 24 * 60 * 60 }),
        ],
      }),
    },

    // --- recomputed nightly; serving 12-hour-old statistics is correct ----
    {
      matcher: ({ url }) =>
        url.pathname.startsWith('/api/analogs') ||
        url.pathname.startsWith('/api/calibration') ||
        url.pathname.startsWith('/api/bundle'),
      handler: new CacheFirst({
        cacheName: 'impacto-analytics',
        plugins: [
          new ExpirationPlugin({ maxEntries: 256, maxAgeSeconds: 24 * 60 * 60 }),
        ],
      }),
    },

    // --- fresh if possible, yesterday's if not, always labelled with age ---
    {
      matcher: ({ url }) =>
        url.pathname.startsWith('/api/digest') ||
        url.pathname.startsWith('/api/alerts'),
      handler: new NetworkFirst({
        cacheName: 'impacto-digest',
        networkTimeoutSeconds: 3,
        plugins: [
          new ExpirationPlugin({ maxEntries: 32, maxAgeSeconds: 24 * 60 * 60 }),
        ],
      }),
    },

    // --- images and icons -------------------------------------------------
    {
      matcher: ({ request }) => request.destination === 'image',
      handler: new CacheFirst({
        cacheName: 'impacto-images',
        plugins: [
          new ExpirationPlugin({ maxEntries: 64, maxAgeSeconds: 30 * 24 * 60 * 60 }),
        ],
      }),
    },

    ...defaultCache,
  ],
  fallbacks: {
    entries: [
      {
        url: OFFLINE_URL,
        matcher: ({ request }) => request.destination === 'document',
      },
    ],
  },
});

serwist.addEventListeners();

// ------------------------------------------------------------ background sync
/**
 * Flush queued mutations when connectivity returns.
 *
 * Android only — iOS has no Background Sync, so the app falls back to flushing
 * on next foreground. That is stated rather than hidden because it changes what
 * an iOS user can be promised.
 */
self.addEventListener('sync', (event) => {
  const syncEvent = event as ExtendableEvent & { tag?: string };
  if (syncEvent.tag !== OUTBOX_TAG) return;

  syncEvent.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({ includeUncontrolled: true });
      // The outbox lives in the page's Dexie instance, so the page does the
      // replay. Duplicating the queue in the worker would create two sources of
      // truth for the same pending edit.
      for (const client of clientList) {
        client.postMessage({ type: 'flush-outbox' });
      }
    })(),
  );
});

// ------------------------------------------------------------------- push
/**
 * Notification payloads carry {alertId, archetypeLabel, severity} and nothing
 * else — never a number. Push bodies are not guardrail-checked at send time, and
 * a stale figure on a lock screen is exactly the wrong failure mode. The full,
 * freshly-checked alert is fetched when the notification is tapped.
 */
self.addEventListener('push', (event) => {
  if (!event.data) return;

  let payload: { alertId?: string; archetypeLabel?: string; severity?: string };
  try {
    payload = event.data.json();
  } catch {
    return;
  }

  const title = payload.archetypeLabel ?? 'Impacto';
  event.waitUntil(
    self.registration.showNotification(title, {
      body:
        payload.severity === 'high'
          ? 'A high-severity event was detected on your watchlist.'
          : 'An event on your watchlist was detected.',
      icon: '/icons/192.png',
      badge: '/icons/192.png',
      tag: payload.alertId,
      data: { alertId: payload.alertId },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const alertId = (event.notification.data as { alertId?: string })?.alertId;
  const target = alertId ? `/?alert=${encodeURIComponent(alertId)}` : '/';

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      });
      const existing = clientList.find((c) => 'focus' in c);
      if (existing) {
        await existing.focus();
        existing.postMessage({ type: 'open-alert', alertId });
        return;
      }
      await self.clients.openWindow(target);
    })(),
  );
});

export {};
