import withSerwistInit from '@serwist/next';
import type { NextConfig } from 'next';

const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The API is proxied under /api so the service worker's caching rules can be
  // written against same-origin paths, and so cookies work without CORS in dev.
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${API_ORIGIN}/:path*` }];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Frame-Options', value: 'DENY' },
        ],
      },
    ];
  },
};

// Serwist compiles app/sw.ts into /sw.js. Disabled in development so a stale
// worker never serves yesterday's bundle while you are editing today's code.
const withSerwist = withSerwistInit({
  swSrc: 'app/sw.ts',
  swDest: 'public/sw.js',
  disable: process.env.NODE_ENV === 'development',
  reloadOnOnline: true,
});

export default withSerwist(nextConfig);
