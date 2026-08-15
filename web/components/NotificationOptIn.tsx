'use client';
// 'use client': touches the Notification and PushManager APIs.

import { useState } from 'react';

import copy from '@/lib/copy/en-IN';
import { api } from '@/lib/api/client';

/**
 * Contextual notification permission.
 *
 * `Notification.requestPermission()` is never called on load — only after the
 * user taps "Notify me", and then only after a pre-permission screen that states
 * exactly what will be sent and how often. A denied permission is permanent in
 * most browsers, so spending it on someone who has not asked for notifications
 * loses the channel for good.
 *
 * A Playwright assertion checks that the browser prompt is not reachable on page
 * load; see tests/e2e/notifications.spec.ts.
 */

type Stage = 'idle' | 'explaining' | 'granted' | 'denied' | 'unsupported';

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const normalised = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(normalised);
  // Allocated over a plain ArrayBuffer: PushManager rejects a view that could
  // be backed by a SharedArrayBuffer.
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export function NotificationOptIn() {
  const [stage, setStage] = useState<Stage>('idle');

  async function subscribe() {
    if (typeof Notification === 'undefined' || !('serviceWorker' in navigator)) {
      setStage('unsupported');
      return;
    }

    // Only now — after the user tapped through the explanation.
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      setStage('denied');
      return;
    }

    try {
      const { publicKey } = await api.pushPublicKey();
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      await api.pushSubscribe(subscription.toJSON() as PushSubscriptionJSON);
      setStage('granted');
    } catch {
      setStage('unsupported');
    }
  }

  if (stage === 'granted') {
    return (
      <p className="m-0 text-sm text-[var(--color-text-secondary)]">
        {copy.notifications.contentNote}
      </p>
    );
  }

  if (stage === 'denied') {
    return (
      <p className="m-0 text-sm text-[var(--color-text-secondary)]">
        {copy.notifications.denied}
      </p>
    );
  }

  if (stage === 'explaining') {
    return (
      <div
        role="dialog"
        aria-labelledby="pre-permission-heading"
        data-testid="pre-permission"
        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3"
      >
        <p id="pre-permission-heading" className="m-0 text-sm font-medium">
          {copy.notifications.prePermissionHeading}
        </p>
        <p className="m-0 mt-1 text-sm text-[var(--color-text-secondary)]">
          {copy.notifications.prePermissionBody}
        </p>
        <p className="m-0 mt-1 text-xs text-[var(--color-muted)]">
          {copy.notifications.prePermissionFrequency}{' '}
          {copy.notifications.contentNote}
        </p>
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => void subscribe()}
            className="rounded-lg bg-[var(--color-text-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-surface-1)]"
          >
            {copy.notifications.prePermissionContinue}
          </button>
          <button
            type="button"
            onClick={() => setStage('idle')}
            className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm"
          >
            {copy.notifications.prePermissionCancel}
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      data-testid="notify-me"
      onClick={() => setStage('explaining')}
      className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm"
    >
      {copy.notifications.enable}
    </button>
  );
}

export default NotificationOptIn;
