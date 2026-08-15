import copy from '@/lib/copy/en-IN';

/**
 * Sticky, not dismissible, on any screen showing a number.
 *
 * Not collapsed behind an info icon and not a one-time toast: under SEBI's
 * Research Analyst and Investment Adviser regulations this is the boundary
 * between a legal product and an unregistered one, and a disclaimer the user has
 * dismissed is not on screen.
 */
export function DisclaimerBar() {
  return (
    <div
      role="note"
      className="sticky bottom-14 z-20 border-t border-[var(--color-border)] bg-[var(--color-surface-1)]/95 px-4 py-2 text-[11px] leading-snug text-[var(--color-muted)] backdrop-blur lg:bottom-0"
    >
      <p className="m-0 mx-auto max-w-5xl">
        {copy.disclaimer.short}{' '}
        <a href="/compliance" className="underline underline-offset-2">
          {copy.nav.compliance}
        </a>
      </p>
    </div>
  );
}

export default DisclaimerBar;
