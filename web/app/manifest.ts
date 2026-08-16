import type { MetadataRoute } from 'next';

/**
 * Web app manifest (§5.3).
 *
 * Portrait-locked and dark-themed: people check markets one-handed, early and
 * late, and a light splash at 06:00 is the first thing they would complain about.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Impacto — Global events, Indian market impact',
    short_name: 'Impacto',
    description:
      'Historical statistics on how global events have moved Indian equity sectors.',
    // The query parameter distinguishes installed launches from browser visits
    // in analytics without needing a separate entry point.
    start_url: '/?source=pwa',
    scope: '/',
    display: 'standalone',
    background_color: '#0d0d0d',
    theme_color: '#0d0d0d',
    orientation: 'portrait',
    lang: 'en-IN',
    categories: ['finance', 'news'],
    icons: [
      { src: '/icons/192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/512.png', sizes: '512x512', type: 'image/png' },
      {
        src: '/icons/maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
    screenshots: [
      {
        src: '/screenshots/mobile-today.png',
        sizes: '1080x1920',
        type: 'image/png',
        form_factor: 'narrow',
      },
      {
        src: '/screenshots/wide-explore.png',
        sizes: '1920x1080',
        type: 'image/png',
        form_factor: 'wide',
      },
    ],
    shortcuts: [
      { name: "Today's digest", url: '/', short_name: 'Today' },
      { name: 'Ask why', url: '/ask', short_name: 'Ask' },
    ],
  };
}
