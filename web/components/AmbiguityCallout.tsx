import copy from '@/lib/copy/en-IN';

/**
 * Shown wherever a rule carries direction: 0.
 *
 * The ambiguity is the information. Collapsing a two-sided linkage into a sign
 * because the interface looks tidier would be inventing a claim the data does
 * not support, so this is deliberately prominent rather than a footnote.
 */
export function AmbiguityCallout({ className = '' }: { className?: string }) {
  return (
    <aside
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-neutral)] px-3 py-2.5 ${className}`}
    >
      <p className="m-0 text-xs font-semibold uppercase tracking-[0.06em] text-[var(--color-text-secondary)]">
        {copy.ambiguity.heading}
      </p>
      <p className="m-0 mt-1 max-w-prose text-sm leading-relaxed text-[var(--color-text-secondary)]">
        {copy.ambiguity.body}
      </p>
    </aside>
  );
}

export default AmbiguityCallout;
