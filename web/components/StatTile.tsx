import EvidenceBadge from './EvidenceBadge';

/**
 * label / value / sub, with a hero variant for the median.
 *
 * `white-space: nowrap` and proportional figures per the mark spec: a figure that
 * wraps mid-number reads as two numbers, and tabular figures in prose look like a
 * spreadsheet cell dropped into a sentence.
 */
export interface StatTileProps {
  label: string;
  value: string;
  sub?: string;
  hero?: boolean;
  tone?: 'pos' | 'neg' | 'neutral' | 'default';
  evidence?: { sampleSize: number; pValue: number; hitRate?: number };
  className?: string;
}

const TONE_CLASS: Record<NonNullable<StatTileProps['tone']>, string> = {
  pos: 'text-[var(--color-pos)]',
  neg: 'text-[var(--color-neg)]',
  neutral: 'text-[var(--color-text-secondary)]',
  default: 'text-[var(--color-text-primary)]',
};

export function StatTile({
  label,
  value,
  sub,
  hero = false,
  tone = 'default',
  evidence,
  className = '',
}: StatTileProps) {
  return (
    <div
      className={`flex flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2.5 ${className}`}
    >
      <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--color-muted)]">
        {label}
      </span>
      <span
        className={`pnum whitespace-nowrap font-semibold tracking-[-0.01em] ${
          hero ? 'text-3xl' : 'text-xl'
        } ${TONE_CLASS[tone]}`}
      >
        {value}
      </span>
      {sub && (
        <span className="text-xs text-[var(--color-text-secondary)]">{sub}</span>
      )}
      {evidence && (
        <EvidenceBadge
          sampleSize={evidence.sampleSize}
          pValue={evidence.pValue}
          hitRate={evidence.hitRate}
        />
      )}
    </div>
  );
}

export default StatTile;
