import type { Metadata } from 'next';

import EvidenceBadge from '@/components/EvidenceBadge';
import copy from '@/lib/copy/en-IN';
import { serverApi } from '@/lib/api/server';
import { bps, formatDate, titleCase } from '@/lib/format';

/**
 * The honesty page. Every encoded prior, scored against realised history.
 *
 * Rules the data rejects are shown as rejected rather than quietly dropped —
 * a calibration record that only lists its wins is marketing, not calibration.
 */
// Next reads this statically, so it must be a literal rather than an
// import. Keep it in step with REVALIDATE_SECONDS in lib/api/server.ts.
export const revalidate = 86_400; // 24 hours

export const metadata: Metadata = {
  title: copy.nav.calibration,
  description: copy.calibration.subtitle,
  alternates: { canonical: '/calibration' },
};

const STATUS_LABEL: Record<string, string> = {
  confirmed: copy.calibration.statusConfirmed,
  sign_ok_magnitude_off: copy.calibration.statusSignOk,
  contradicted: copy.calibration.statusContradicted,
  underpowered: copy.calibration.statusUnderpowered,
  no_data: copy.calibration.statusNoData,
};

const STATUS_TONE: Record<string, string> = {
  confirmed: 'var(--color-good)',
  sign_ok_magnitude_off: 'var(--color-warning)',
  contradicted: 'var(--color-critical)',
  underpowered: 'var(--color-baseline)',
  no_data: 'var(--color-baseline)',
};

export default async function CalibrationPage() {
  const report = await serverApi.calibration();

  if (!report) {
    return <p className="text-sm">{copy.errors.generic}</p>;
  }

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
          {copy.calibration.title}
        </h1>
        <p className="mt-1 max-w-prose text-sm text-[var(--color-text-secondary)]">
          {copy.calibration.subtitle}
        </p>
        {report.run_at && (
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            {copy.calibration.lastRun} {formatDate(report.run_at)}
          </p>
        )}
      </header>

      <section className="flex flex-wrap gap-2">
        {Object.entries(report.summary).map(([status, count]) => (
          <div
            key={status}
            className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2"
          >
            <span
              aria-hidden="true"
              className="h-2 w-2 rounded-full"
              style={{ background: STATUS_TONE[status] ?? 'var(--color-baseline)' }}
            />
            <span className="text-sm font-medium tnum">{count}</span>
            <span className="text-xs text-[var(--color-text-secondary)]">
              {STATUS_LABEL[status] ?? status}
            </span>
          </div>
        ))}
      </section>

      <section className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <caption className="sr-only">{copy.calibration.title}</caption>
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-xs uppercase tracking-[0.06em] text-[var(--color-muted)]">
              <th scope="col" className="py-1.5 pr-3 font-normal">Archetype</th>
              <th scope="col" className="py-1.5 pr-3 font-normal">{copy.explore.targetLabel}</th>
              <th scope="col" className="py-1.5 pr-3 font-normal">{copy.explore.priorHeading}</th>
              <th scope="col" className="py-1.5 pr-3 font-normal">{copy.explore.realisedHeading}</th>
              <th scope="col" className="py-1.5 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((row) => (
              <tr
                key={`${row.archetype}-${row.target}`}
                className="border-b border-[var(--color-border)] last:border-b-0"
              >
                <td className="py-1.5 pr-3">{titleCase(row.archetype)}</td>
                <td className="py-1.5 pr-3 text-[var(--color-text-secondary)]">
                  {titleCase(row.target)}
                </td>
                <td className="tnum py-1.5 pr-3 whitespace-nowrap text-[var(--color-text-secondary)]">
                  {row.prior_range_bps
                    ? `${bps(row.prior_range_bps[0])} … ${bps(row.prior_range_bps[1])}`
                    : '—'}
                </td>
                <td className="py-1.5 pr-3 whitespace-nowrap">
                  {row.realised_median_bps !== undefined ? (
                    <EvidenceBadge
                      sampleSize={row.sample_size}
                      pValue={row.p_value ?? 1}
                      hitRate={row.hit_rate}
                    >
                      <span className="tnum text-sm font-medium">
                        {bps(row.realised_median_bps)}
                      </span>
                    </EvidenceBadge>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="py-1.5">
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span
                      aria-hidden="true"
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{
                        background: STATUS_TONE[row.status] ?? 'var(--color-baseline)',
                      }}
                    />
                    {STATUS_LABEL[row.status] ?? row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
