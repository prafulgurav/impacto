import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import AmbiguityCallout from '@/components/AmbiguityCallout';
import ChannelChip from '@/components/ChannelChip';
import EvidenceBadge from '@/components/EvidenceBadge';
import StatTile from '@/components/StatTile';
import CarDistribution from '@/components/charts/CarDistribution';
import copy from '@/lib/copy/en-IN';
import { serverApi } from '@/lib/api/server';
import { bps, formatDate, realisedTone, titleCase } from '@/lib/format';

/** The deep dive: full analog table and the distribution behind the median. */

// Next reads this statically, so it must be a literal rather than an
// import. Keep it in step with REVALIDATE_SECONDS in lib/api/server.ts.
export const revalidate = 86_400; // 24 hours
export const dynamicParams = true;

export async function generateStaticParams() {
  const archetypes = await serverApi.archetypes();
  return (archetypes ?? []).flatMap((archetype) =>
    archetype.targets.map((target) => ({
      archetype: archetype.id,
      target,
    })),
  );
}

type Props = { params: Promise<{ archetype: string; target: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { archetype: id, target } = await params;
  const archetype = await serverApi.archetype(id);
  if (!archetype) return { title: copy.errors.notFound };

  const title = `${archetype.label} and ${titleCase(target)}`;
  return {
    title,
    description: `What ${titleCase(target)} did after past occurrences of ${archetype.label}, with the full sample.`,
    alternates: { canonical: `/explore/${id}/${target}` },
  };
}

export default async function TargetPage({ params }: Props) {
  const { archetype: id, target } = await params;
  const [archetype, channels, summary] = await Promise.all([
    serverApi.archetype(id),
    serverApi.channels(),
    serverApi.analogs(id, target),
  ]);

  if (!archetype) notFound();

  const impact = archetype.impacts.find((i) => i.target === target);
  if (!impact) notFound();

  const channelsById = new Map((channels ?? []).map((c) => [c.id, c]));
  const impactChannels = impact.channels
    .map((cid) => channelsById.get(cid))
    .filter((c): c is NonNullable<typeof c> => Boolean(c));

  return (
    <article className="flex flex-col gap-6">
      <header>
        <p className="m-0 text-xs uppercase tracking-[0.06em] text-[var(--color-muted)]">
          <a href={`/explore/${archetype.id}`} className="underline underline-offset-2">
            {archetype.label}
          </a>
        </p>
        <h1 className="m-0 mt-1 text-2xl font-semibold tracking-[-0.02em]">
          {titleCase(target)}
        </h1>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {impact.rationale}
        </p>
      </header>

      {impact.direction === 0 && <AmbiguityCallout />}

      {summary && summary.sample_size > 0 ? (
        <>
          <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile
              label={copy.evidence.median}
              value={`${bps(summary.median_car_bps)} ${copy.evidence.unitBps}`}
              hero
              tone={realisedTone(summary.median_car_bps)}
              evidence={{
                sampleSize: summary.sample_size,
                pValue: summary.p_value,
                hitRate: summary.hit_rate,
              }}
            />
            <StatTile
              label={copy.evidence.mean}
              value={`${bps(summary.mean_car_bps)} ${copy.evidence.unitBps}`}
              tone={realisedTone(summary.mean_car_bps)}
              evidence={{ sampleSize: summary.sample_size, pValue: summary.p_value }}
            />
            <StatTile
              label={copy.evidence.range}
              value={`${bps(summary.p5_bps)} … ${bps(summary.p95_bps)}`}
              sub={copy.evidence.unitBpsFull}
              evidence={{ sampleSize: summary.sample_size, pValue: summary.p_value }}
            />
            <StatTile
              label={copy.explore.priorHeading}
              value={`${bps(impact.magnitude_prior_bps[0])} … ${bps(impact.magnitude_prior_bps[1])}`}
              sub={`${impact.confidence} confidence · ${impact.horizon}`}
            />
          </section>

          <section>
            <h2 className="m-0 mb-2 text-sm font-semibold">
              {copy.explore.distributionHeading}
            </h2>
            <CarDistribution
              points={summary.analogs.map((a) => ({
                eventId: a.event_id,
                eventDate: a.event_date,
                headline: a.headline,
                carBps: a.car_bps,
              }))}
              medianBps={summary.median_car_bps}
            />
          </section>

          <section>
            <h2 id="analogs-heading" className="m-0 mb-2 text-sm font-semibold">
              {copy.explore.analogsHeading}
            </h2>
            {/* Wide content scrolls inside its own container; the page body
                must never scroll horizontally on a 360px screen. Because it
                scrolls, it also has to be focusable — otherwise the columns
                past 360px are unreachable without a pointer. */}
            <div
              className="overflow-x-auto"
              tabIndex={0}
              role="region"
              aria-labelledby="analogs-heading"
            >
              <table className="w-full min-w-[420px] border-collapse text-sm">
                <caption className="sr-only">
                  {copy.explore.analogsHeading}
                </caption>
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-[0.06em] text-[var(--color-muted)]">
                    <th scope="col" className="py-1.5 pr-3 font-normal">
                      Date
                    </th>
                    <th scope="col" className="py-1.5 pr-3 font-normal">
                      Event
                    </th>
                    <th scope="col" className="py-1.5 text-right font-normal">
                      {copy.charts.axisCar}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {summary.analogs.map((analog) => (
                    <tr
                      key={analog.event_id}
                      className="border-b border-[var(--color-border)] last:border-b-0"
                    >
                      <td className="py-1.5 pr-3 whitespace-nowrap text-[var(--color-text-secondary)]">
                        {formatDate(analog.event_date)}
                      </td>
                      <td className="py-1.5 pr-3">{analog.headline}</td>
                      <td
                        className="tnum py-1.5 text-right font-medium"
                        style={{
                          color: `var(--color-${realisedTone(analog.car_bps)})`,
                        }}
                      >
                        {bps(analog.car_bps)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2">
              <EvidenceBadge
                sampleSize={summary.sample_size}
                pValue={summary.p_value}
                hitRate={summary.hit_rate}
              />
            </div>
          </section>
        </>
      ) : (
        <p className="max-w-prose text-sm text-[var(--color-text-secondary)]">
          {copy.explore.noAnalogs}
        </p>
      )}

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.explore.channelsHeading}
        </h2>
        <div className="flex flex-wrap gap-2">
          {impactChannels.map((channel) => (
            <ChannelChip key={channel.id} channel={channel} />
          ))}
        </div>
      </section>
    </article>
  );
}
