'use client';
// 'use client': listens to online/offline and reads IndexedDB.

import { useEffect, useState } from 'react';

import copy from '@/lib/copy/en-IN';
import { formatDataAge } from '@/lib/format';

/**
 * Shows DATA AGE, not just connection state.
 *
 * "You're offline" tells a user nothing about whether the figure in front of
 * them is two minutes or two weeks old. For a product whose whole claim is that
 * its numbers are auditable, the timestamp is the load-bearing part.
 */
export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  const [age, setAge] = useState<string | null>(null);

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);

  useEffect(() => {
    if (!offline) return;
    // Dynamic for the same reason as SyncProvider: this component is in the root
    // layout, and the data age is only needed once we are actually offline.
    void import('@/lib/db/sync').then(({ dataAge }) => {
      void dataAge().then(setAge);
    });
  }, [offline]);

  if (!offline) return null;

  return (
    <div
      role="status"
      data-testid="offline-banner"
      className="border-b border-[var(--color-border)] bg-[var(--color-neutral)] px-4 py-2 text-xs text-[var(--color-text-secondary)]"
    >
      <p className="m-0 mx-auto max-w-5xl">
        {age ? (
          <>
            {copy.offline.bannerShowing}{' '}
            <time dateTime={age} data-testid="data-age">
              {formatDataAge(age)}
            </time>
            . {copy.offline.bannerOffline}
          </>
        ) : (
          copy.offline.bannerOffline
        )}
      </p>
    </div>
  );
}

export default OfflineBanner;
