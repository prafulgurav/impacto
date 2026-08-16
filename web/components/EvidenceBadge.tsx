import copy from '@/lib/copy/en-IN';
import { isNoise, pValue, percent } from '@/lib/format';

/**
 * The most important small component in the app.
 *
 * Every number on screen is wrapped in one of these — no exceptions. A median
 * with no sample size and no p-value is not shippable, and putting the caveat in
 * a footnote instead of beside the figure is the same failure with extra steps.
 * When p > 0.10 the badge says plainly that the distribution is not
 * distinguishable from noise, in the same visual block as the number.
 */
export interface EvidenceBadgeProps {
  /** Number of past occurrences the statistic is drawn from. */
  sampleSize: number;
  pValue: number;
  hitRate?: number;
  /** The figure this badge qualifies. Rendered above the evidence line. */
  children?: React.ReactNode;
  className?: string;
}

export function EvidenceBadge({
  sampleSize,
  pValue: p,
  hitRate,
  children,
  className = '',
}: EvidenceBadgeProps) {
  const noise = isNoise(p);

  return (
    <span className={`inline-flex flex-col gap-0.5 ${className}`}>
      {children}
      <span
        className={`text-[11px] leading-tight tnum ${
          noise ? 'text-[var(--color-muted)]' : 'text-[var(--color-text-secondary)]'
        }`}
        // One label for the whole evidence line, so a screen reader announces
        // the caveat with the figure rather than as loose fragments.
        aria-label={
          `Based on ${sampleSize} past occurrences, p equals ${pValue(p)}` +
          (noise ? `. ${copy.evidence.noise}` : '')
        }
      >
        <span>
          {copy.evidence.sampleSize}={sampleSize}
        </span>
        <span aria-hidden="true"> · </span>
        <span>
          {copy.evidence.pValue}={pValue(p)}
        </span>
        {hitRate !== undefined && (
          <>
            <span aria-hidden="true"> · </span>
            <span>
              {percent(hitRate)} {copy.evidence.hitRate}
            </span>
          </>
        )}
        {noise && (
          <>
            <span aria-hidden="true"> · </span>
            <span className="italic">{copy.evidence.noise}</span>
          </>
        )}
      </span>
    </span>
  );
}

export default EvidenceBadge;
