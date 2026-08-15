import type { MetadataRoute } from 'next';

import { serverApi } from '@/lib/api/server';

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://impacto.app';

/** Every static page plus every archetype and archetype/target page. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const archetypes = (await serverApi.archetypes()) ?? [];
  const now = new Date();

  const staticRoutes = [
    { url: '/', priority: 1 },
    { url: '/explore', priority: 0.9 },
    { url: '/calibration', priority: 0.8 },
    { url: '/methodology', priority: 0.6 },
    { url: '/compliance', priority: 0.5 },
    { url: '/ask', priority: 0.7 },
  ].map((route) => ({
    url: `${SITE}${route.url}`,
    lastModified: now,
    changeFrequency: 'daily' as const,
    priority: route.priority,
  }));

  const archetypeRoutes = archetypes.map((a) => ({
    url: `${SITE}/explore/${a.id}`,
    lastModified: now,
    changeFrequency: 'daily' as const,
    priority: 0.9,
  }));

  const targetRoutes = archetypes.flatMap((a) =>
    a.targets.map((target) => ({
      url: `${SITE}/explore/${a.id}/${target}`,
      lastModified: now,
      changeFrequency: 'daily' as const,
      priority: 0.7,
    })),
  );

  return [...staticRoutes, ...archetypeRoutes, ...targetRoutes];
}
