'use client';
// 'use client': captures beforeinstallprompt and reads engagement from storage.

import { useEffect, useState } from 'react';

import copy from '@/lib/copy/en-IN';

/**
 * Deferred install prompt.
 *
 * Prompting on first paint is the single most common PWA mistake and it
 * permanently poisons the install rate — you get one shot per user, and a
 * dismissal is remembered by the browser as well as by us. So the banner only
 * appears when all three hold: this is the user's 2nd+ session, they have spent
 * more than 60 seconds in the app, and they have not dismissed it in 30 days.
 */

const SESSIONS_KEY = 'impacto-sessions';
const TIME_KEY = 'impacto-seconds';
const DISMISSED_KEY = 'impacto-install-dismissed';

const MIN_SESSIONS = 2;
const MIN_SECONDS = 60;
const DISMISS_DAYS = 30;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

function readNumber(key: string): number {
  try {
    return Number(localStorage.getItem(key) ?? 0);
  } catch {
    return 0;
  }
}

export function eligible(
  sessions: number,
  seconds: number,
  dismissedAt: number | null,
  now = Date.now(),
): boolean {
  if (sessions < MIN_SESSIONS) return false;
  if (seconds < MIN_SECONDS) return false;
  if (dismissedAt && now - dismissedAt < DISMISS_DAYS * 24 * 3600 * 1000) {
    return false;
  }
  return true;
}

export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);

  // Session and dwell-time accounting. Cheap, and entirely local.
  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_KEY, String(readNumber(SESSIONS_KEY) + 1));
    } catch {
      return;
    }
    const started = Date.now();
    const tick = setInterval(() => {
      try {
        const elapsed = Math.round((Date.now() - started) / 1000);
        localStorage.setItem(TIME_KEY, String(readNumber(TIME_KEY) + 5));
        void elapsed;
      } catch {
        clearInterval(tick);
      }
    }, 5000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      // Suppress the browser's own banner so we control the moment.
      event.preventDefault();
      setDeferred(event as BeforeInstallPromptEvent);

      const dismissed = localStorage.getItem(DISMISSED_KEY);
      if (
        eligible(
          readNumber(SESSIONS_KEY),
          readNumber(TIME_KEY),
          dismissed ? Number(dismissed) : null,
        )
      ) {
        setVisible(true);
      }
    };

    window.addEventListener('beforeinstallprompt', onPrompt);
    return () => window.removeEventListener('beforeinstallprompt', onPrompt);
  }, []);

  if (!visible || !deferred) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="install-heading"
      data-testid="install-prompt"
      className="fixed inset-x-3 bottom-20 z-40 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3 shadow-lg lg:inset-x-auto lg:right-6 lg:bottom-6 lg:w-80"
    >
      <p id="install-heading" className="m-0 text-sm font-medium">
        {copy.install.heading}
      </p>
      <p className="m-0 mt-1 text-xs text-[var(--color-text-secondary)]">
        {copy.install.body}
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={() => {
            void deferred.prompt();
            setVisible(false);
          }}
          className="rounded-lg bg-[var(--color-text-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-surface-1)]"
        >
          {copy.install.accept}
        </button>
        <button
          type="button"
          onClick={() => {
            try {
              localStorage.setItem(DISMISSED_KEY, String(Date.now()));
            } catch {
              // Nothing to persist to; the banner simply reappears next session.
            }
            setVisible(false);
          }}
          className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm"
        >
          {copy.install.dismiss}
        </button>
      </div>
    </div>
  );
}

/**
 * iOS has no install prompt, no Background Sync, and no Web Push until the app
 * has been added to the home screen. That is an education step, not a bug, and
 * hiding it would mean promising iOS users notifications they never receive.
 */
export function IosInstallHint() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const ua = navigator.userAgent;
    const isIos = /iPad|iPhone|iPod/.test(ua);
    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    setShow(isIos && !standalone);
  }, []);

  if (!show) return null;

  return (
    <aside
      data-testid="ios-install-hint"
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-neutral)] p-3"
    >
      <p className="m-0 text-sm font-medium">{copy.install.iosHeading}</p>
      <p className="m-0 mt-1 text-xs text-[var(--color-text-secondary)]">
        {copy.install.iosBody}
      </p>
    </aside>
  );
}

export default InstallPrompt;
