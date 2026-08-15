import type { Metadata, Viewport } from 'next';

import DisclaimerBar from '@/components/DisclaimerBar';
import InstallPrompt from '@/components/InstallPrompt';
import OfflineBanner from '@/components/OfflineBanner';
import SyncProvider from '@/components/SyncProvider';
import { BottomTabBar, Sidebar } from '@/components/shell/Navigation';
import copy from '@/lib/copy/en-IN';

import './globals.css';

export const metadata: Metadata = {
  title: {
    default: `${copy.app.name} — ${copy.app.tagline}`,
    template: `%s · ${copy.app.name}`,
  },
  description: copy.app.description,
  applicationName: copy.app.name,
  manifest: '/manifest.webmanifest',
  appleWebApp: { capable: true, title: copy.app.name, statusBarStyle: 'default' },
  openGraph: {
    type: 'website',
    siteName: copy.app.name,
    title: `${copy.app.name} — ${copy.app.tagline}`,
    description: copy.app.description,
    locale: 'en_IN',
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f9f9f7' },
    { media: '(prefers-color-scheme: dark)', color: '#0d0d0d' },
  ],
};

/**
 * Applies the persisted theme before first paint.
 *
 * Inline and blocking on purpose: running this after hydration would show a
 * light flash to every dark-mode user on every cold launch, which on the phone
 * this product targets is the first thing they would notice.
 */
const THEME_SCRIPT = `
(function () {
  try {
    var t = localStorage.getItem('impacto-theme');
    if (t === 'light' || t === 'dark') {
      document.documentElement.setAttribute('data-theme', t);
    }
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-[var(--color-surface-1)] focus:px-3 focus:py-2"
        >
          {copy.nav.skipToContent}
        </a>

        <SyncProvider>
          <div className="flex min-h-dvh">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <OfflineBanner />
              <main id="main" className="flex-1 px-4 pb-24 pt-4 lg:px-8 lg:pb-8">
                <div className="mx-auto w-full max-w-5xl">{children}</div>
              </main>
              <DisclaimerBar />
            </div>
          </div>
          <BottomTabBar />
          <InstallPrompt />
        </SyncProvider>
      </body>
    </html>
  );
}
