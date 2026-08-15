'use client';
// 'use client': reads IndexedDB first and paints before any network call.

import { useEffect, useState } from 'react';
import Link from 'next/link';

import copy from '@/lib/copy/en-IN';
import { api } from '@/lib/api/client';
import type { Alert, Digest } from '@/lib/api/client';
import { formatDate } from '@/lib/format';

/**
 * Today.
 *
 * Read-through rendering: IndexedDB first, paint, then reconcile with the
 * network. A warm launch therefore never shows a spinner, which is the whole
 * reason for the offline layer — on the phone this targets, the network is the
 * slowest thing in the system.
 */
export default function TodayPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    // 1. Local first. This is the paint that matters.
    void (async () => {
      try {
        const { db } = await import('@/lib/db/dexie');
        const stored = await db().digests.orderBy('digestDate').last();
        if (!cancelled && stored) {
          setDigest(stored.payload);
          setReady(true);
        }
      } catch {
        // No IndexedDB (private mode, or a first run) — fall through to network.
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    // 2. Reconcile. Failure here is silent: whatever was painted still stands.
    void (async () => {
      try {
        const [fresh, activeAlerts] = await Promise.all([
          api.digest(),
          api.alerts().catch(() => [] as Alert[]),
        ]);
        if (cancelled) return;
        setDigest(fresh);
        setAlerts(activeAlerts);
      } catch {
        // Offline, or the API is down. The cached digest is the answer.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return <p className="sr-only">{copy.a11y.loading}</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
          {copy.today.title}
        </h1>
        {digest && (
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            {copy.today.generatedAt} {formatDate(digest.digest_date)}
          </p>
        )}
      </header>

      {digest ? (
        <section>
          <h2 className="m-0 mb-2 text-sm font-semibold">
            {copy.today.digestHeading}
          </h2>
          <p className="m-0 max-w-prose text-sm leading-relaxed">
            {digest.headline_summary}
          </p>
          <div className="mt-3 flex flex-col gap-3">
            {digest.sections.map((section) => (
              <div key={section.title}>
                <h3 className="m-0 text-xs uppercase tracking-[0.06em] text-[var(--color-muted)]">
                  {section.title}
                </h3>
                <ul className="m-0 mt-1 flex list-disc flex-col gap-1 pl-5 text-sm text-[var(--color-text-secondary)]">
                  {section.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section>
          <p className="m-0 max-w-prose text-sm">{copy.today.empty}</p>
          <p className="m-0 mt-1 max-w-prose text-sm text-[var(--color-text-secondary)]">
            {copy.today.emptyHint}
          </p>
        </section>
      )}

      {alerts.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 text-sm font-semibold">
            {copy.today.alertsHeading}
          </h2>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {alerts.map((alert) => (
              <li
                key={alert.alert_id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3"
              >
                <div className="flex items-baseline gap-2">
                  <SeverityDot severity={alert.severity} />
                  <span className="text-sm font-medium">{alert.headline}</span>
                </div>
                <p className="m-0 mt-1 text-sm text-[var(--color-text-secondary)]">
                  {alert.body}
                </p>
                <Link
                  href={`/explore/${alert.archetype_id}`}
                  className="mt-1.5 inline-block text-xs underline underline-offset-2"
                >
                  {copy.today.viewDetail}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Severity is never carried by colour alone — the label is always present. */
function SeverityDot({ severity }: { severity: Alert['severity'] }) {
  const tone =
    severity === 'high'
      ? 'var(--color-critical)'
      : severity === 'watch'
        ? 'var(--color-warning)'
        : 'var(--color-baseline)';
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-[11px] uppercase tracking-[0.06em] text-[var(--color-muted)]">
      <span
        aria-hidden="true"
        className="h-2 w-2 rounded-full"
        style={{ background: tone }}
      />
      {severity}
    </span>
  );
}
