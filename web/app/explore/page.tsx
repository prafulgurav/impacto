import type { Metadata } from 'next';
import Link from 'next/link';

import copy from '@/lib/copy/en-IN';
import { serverApi } from '@/lib/api/server';
import { titleCase } from '@/lib/format';

// Next reads this statically, so it must be a literal rather than an
// import. Keep it in step with REVALIDATE_SECONDS in lib/api/server.ts.
export const revalidate = 86_400; // 24 hours

export const metadata: Metadata = {
  title: copy.nav.explore,
  description: copy.explore.subtitle,
  alternates: { canonical: '/explore' },
};

// Server Component: this page is pure content and needs no interactivity.
export default async function ExplorePage() {
  const archetypes = (await serverApi.archetypes()) ?? [];

  const families = archetypes.reduce<Record<string, typeof archetypes>>(
    (acc, archetype) => {
      (acc[archetype.family] ??= []).push(archetype);
      return acc;
    },
    {},
  );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
          {copy.explore.title}
        </h1>
        <p className="mt-1 max-w-prose text-sm text-[var(--color-text-secondary)]">
          {copy.explore.subtitle}
        </p>
      </header>

      {Object.entries(families).map(([family, items]) => (
        <section key={family}>
          <h2 className="m-0 mb-2 text-xs uppercase tracking-[0.06em] text-[var(--color-muted)]">
            {titleCase(family)}
          </h2>
          <ul className="m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2">
            {items.map((archetype) => (
              <li key={archetype.id}>
                <Link
                  href={`/explore/${archetype.id}`}
                  className="flex h-full flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3 transition-colors hover:border-[var(--color-baseline)]"
                >
                  <span className="text-sm font-medium">{archetype.label}</span>
                  <span className="line-clamp-2 text-xs text-[var(--color-text-secondary)]">
                    {archetype.description}
                  </span>
                  <span className="mt-auto pt-1 text-[11px] text-[var(--color-muted)]">
                    {archetype.n_impacts} encoded linkages
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
