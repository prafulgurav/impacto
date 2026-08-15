'use client';
// 'use client': reads local sync state and drives auth and permission flows.

import { useEffect, useState } from 'react';

import NotificationOptIn from '@/components/NotificationOptIn';
import ThemeToggle from '@/components/shell/ThemeToggle';
import { IosInstallHint } from '@/components/InstallPrompt';
import copy from '@/lib/copy/en-IN';
import { ApiError, api, setAccessToken } from '@/lib/api/client';
import type { MeResponse } from '@/lib/api/client';
import { formatDataAge } from '@/lib/format';

export default function SettingsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [queued, setQueued] = useState(0);
  const [email, setEmail] = useState('');
  const [linkSent, setLinkSent] = useState(false);

  useEffect(() => {
    void api
      .me()
      .then(setMe)
      .catch((error) => {
        if (!(error instanceof ApiError && error.kind === 'unauthorized')) return;
      });
    void import('@/lib/db/dexie').then(({ META_KEYS, getMeta, pending }) => {
      void getMeta<string>(META_KEYS.lastSyncAt).then((v) => setLastSync(v ?? null));
      void pending().then((entries) => setQueued(entries.length));
    });
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
        {copy.settings.title}
      </h1>

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.settings.themeHeading}
        </h2>
        <ThemeToggle />
      </section>

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.settings.accountHeading}
        </h2>
        {me ? (
          <div className="flex flex-col gap-2">
            <p className="m-0 text-sm text-[var(--color-text-secondary)]">
              {me.user.email}
            </p>
            <button
              type="button"
              onClick={() => {
                void api.logout().finally(() => {
                  setAccessToken(null);
                  setMe(null);
                });
              }}
              className="self-start rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm"
            >
              {copy.auth.signOut}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="m-0 max-w-prose text-sm text-[var(--color-text-secondary)]">
              {copy.auth.whyBody}
            </p>
            <p className="m-0 max-w-prose text-xs text-[var(--color-muted)]">
              {copy.auth.withoutBody}
            </p>
            <form
              className="flex flex-wrap gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                void api.magicLink(email).then(() => setLinkSent(true));
              }}
            >
              <label htmlFor="email" className="sr-only">
                {copy.auth.emailLabel}
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-1.5 text-sm"
              />
              <button
                type="submit"
                className="rounded-lg bg-[var(--color-text-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-surface-1)]"
              >
                {copy.auth.magicLink}
              </button>
            </form>
            {linkSent && (
              <p role="status" className="m-0 text-xs text-[var(--color-text-secondary)]">
                {copy.auth.magicLinkSent}
              </p>
            )}
          </div>
        )}
      </section>

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.settings.notificationsHeading}
        </h2>
        <NotificationOptIn />
      </section>

      <IosInstallHint />

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.settings.offlineHeading}
        </h2>
        <p className="m-0 text-sm text-[var(--color-text-secondary)]">
          {copy.settings.lastSync}{' '}
          {lastSync ? formatDataAge(lastSync) : '—'}
        </p>
        {queued > 0 && (
          <p className="m-0 mt-1 text-sm text-[var(--color-text-secondary)]">
            {copy.offline.queuedHeading}: {queued}
          </p>
        )}
        <button
          type="button"
          onClick={() => {
            void import('@/lib/db/sync').then(({ clearLocalData }) =>
              clearLocalData().then(() => setLastSync(null)),
            );
          }}
          className="mt-2 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm"
        >
          {copy.settings.clearData}
        </button>
      </section>
    </div>
  );
}
