import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import AmbiguityCallout from '@/components/AmbiguityCallout';
import ChannelChip from '@/components/ChannelChip';
import ImpactBars, { type ImpactBarRow } from '@/components/charts/ImpactBars';
import copy from '@/lib/copy/en-IN';
import { serverApi } from '@/lib/api/server';
import { titleCase } from '@/lib/format';

/**
 * The SEO and LLM-citation surface.
 *
 * Statically generated with ISR at 24 hours, and every number is present in the
 * server-rendered HTML. This is the page Google indexes and the one an assistant
 * cites when someone asks how Fed rate hikes affect Indian IT stocks — so content
 * behind a client-side fetch would be content that does not exist for either.
 */

// Next reads this statically, so it must be a literal rather than an
// import. Keep it in step with REVALIDATE_SECONDS in lib/api/server.ts.
export const revalidate = 86_400; // 24 hours
export const dynamicParams = true;

export async function generateStaticParams() {
  const archetypes = await serverApi.archetypes();
  return (archetypes ?? []).map((a) => ({ archetype: a.id }));
}

type Props = { params: Promise<{ archetype: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { archetype: id } = await params;
  const archetype = await serverApi.archetype(id);
  if (!archetype) return { title: copy.errors.notFound };

  const title = `${archetype.label} — Indian market impact`;
  return {
    title,
    description: archetype.description,
    alternates: { canonical: `/explore/${archetype.id}` },
    openGraph: { title, description: archetype.description, type: 'article' },
  };
}

export default async function ArchetypePage({ params }: Props) {
  const { archetype: id } = await params;
  const [archetype, channels] = await Promise.all([
    serverApi.archetype(id),
    serverApi.channels(),
  ]);

  if (!archetype) notFound();

  const channelsById = new Map((channels ?? []).map((c) => [c.id, c]));

  // Fetched at build time so the statistics are in the HTML, not fetched later.
  const summaries = await Promise.all(
    archetype.impacts.map((impact) =>
      serverApi.analogs(archetype.id, impact.target),
    ),
  );

  const rows: ImpactBarRow[] = archetype.impacts.map((impact, index) => {
    const summary = summaries[index];
    return {
      target: impact.target,
      label: titleCase(impact.target),
      direction: impact.direction,
      priorLowBps: impact.magnitude_prior_bps[0],
      priorHighBps: impact.magnitude_prior_bps[1],
      realisedMedianBps: summary?.median_car_bps ?? null,
      sampleSize: summary?.sample_size ?? 0,
      pValue: summary?.p_value ?? 1,
    };
  });

  const hasTwoSided = archetype.impacts.some((i) => i.direction === 0);
  const usedChannels = [
    ...new Set(archetype.impacts.flatMap((i) => i.channels)),
  ]
    .map((cid) => channelsById.get(cid))
    .filter((c): c is NonNullable<typeof c> => Boolean(c));

  const faq = buildFaq(archetype.label, rows);

  return (
    <article className="flex flex-col gap-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(articleJsonLd(archetype, faq)),
        }}
      />

      <header>
        <p className="m-0 text-xs uppercase tracking-[0.06em] text-[var(--color-muted)]">
          {titleCase(archetype.family)}
        </p>
        <h1 className="m-0 mt-1 text-2xl font-semibold tracking-[-0.02em]">
          {archetype.label}
        </h1>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {archetype.description}
        </p>
      </header>

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.explore.impactsHeading}
        </h2>
        <ImpactBars rows={rows} />
      </section>

      {hasTwoSided && <AmbiguityCallout />}

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.explore.channelsHeading}
        </h2>
        <div className="flex flex-wrap gap-2">
          {usedChannels.map((channel) => (
            <ChannelChip key={channel.id} channel={channel} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.explore.rationaleHeading}
        </h2>
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {archetype.impacts.map((impact, index) => {
            const summary = summaries[index];
            return (
              <li
                key={impact.target}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="m-0 text-sm font-medium">
                    {titleCase(impact.target)}
                  </h3>
                  <Link
                    href={`/explore/${archetype.id}/${impact.target}`}
                    className="text-xs underline underline-offset-2"
                  >
                    {copy.explore.seeTarget}
                  </Link>
                </div>
                <p className="m-0 mt-1.5 max-w-prose text-sm leading-relaxed text-[var(--color-text-secondary)]">
                  {impact.rationale}
                </p>
                {summary === null && (
                  <p className="m-0 mt-1.5 text-xs italic text-[var(--color-muted)]">
                    {copy.explore.noAnalogs}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </article>
  );
}

interface FaqEntry {
  question: string;
  answer: string;
}

/**
 * FAQ entries are generated from the measured statistics rather than written by
 * hand, so they cannot drift from what the page actually shows. Every answer is
 * historical and carries its sample size.
 */
function buildFaq(label: string, rows: ImpactBarRow[]): FaqEntry[] {
  return rows
    .filter((row) => row.realisedMedianBps !== null && row.sampleSize > 0)
    .slice(0, 5)
    .map((row) => ({
      question: `What historically happened to ${row.label} after ${label}?`,
      answer:
        `Across ${row.sampleSize} past occurrences, ${row.label} recorded a median ` +
        `cumulative abnormal return of ${Math.round(row.realisedMedianBps!)} basis points ` +
        `(p = ${row.pValue.toFixed(3)})` +
        (row.pValue > 0.1
          ? ', a distribution not statistically distinguishable from zero.'
          : '.'),
    }));
}

function articleJsonLd(
  archetype: { id: string; label: string; description: string },
  faq: FaqEntry[],
) {
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: `${archetype.label} — Indian market impact`,
      description: archetype.description,
      author: { '@type': 'Organization', name: copy.app.name },
      publisher: { '@type': 'Organization', name: copy.app.name },
      isAccessibleForFree: true,
    },
    ...(faq.length
      ? [
          {
            '@context': 'https://schema.org',
            '@type': 'FAQPage',
            mainEntity: faq.map((entry) => ({
              '@type': 'Question',
              name: entry.question,
              acceptedAnswer: { '@type': 'Answer', text: entry.answer },
            })),
          },
        ]
      : []),
  ];
}
