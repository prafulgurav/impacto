import type { MetadataRoute } from 'next';

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://impacto.app';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        // Nothing under these is public, and none of it is useful to a crawler.
        disallow: ['/api/', '/settings', '/portfolio'],
      },
    ],
    sitemap: `${SITE}/sitemap.xml`,
  };
}
