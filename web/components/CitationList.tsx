'use client';
// 'use client': collapsible.

import { useState } from 'react';

import copy from '@/lib/copy/en-IN';

export interface Citation {
  label: string;
  kind: string;
  detail: string;
}

/**
 * Under every explainer answer.
 *
 * When there are no citations the "no global event explains this" state is
 * rendered instead of a bare answer — an uncited claim is exactly what this
 * architecture exists to prevent, so the absence has to be visible.
 */
export function CitationList({
  citations,
  defaultOpen = true,
}: {
  citations: Citation[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  if (citations.length === 0) {
    return (
      <p
        data-testid="no-citations"
        className="m-0 mt-3 max-w-prose rounded-lg border border-[var(--color-border)] bg-[var(--color-neutral)] px-3 py-2 text-sm text-[var(--color-text-secondary)]"
      >
        {copy.ask.noCitations}
      </p>
    );
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-xs font-medium uppercase tracking-[0.06em] text-[var(--color-muted)] underline underline-offset-2"
      >
        {copy.ask.citationsHeading} ({citations.length})
      </button>
      {open && (
        <ul className="m-0 mt-1.5 flex list-none flex-col gap-1 p-0">
          {citations.map((citation, index) => (
            <li
              key={`${citation.label}-${index}`}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface-1)] px-2.5 py-1.5 text-xs"
            >
              <span className="font-medium">{citation.label}</span>
              <span className="text-[var(--color-text-secondary)]">
                {' '}
                — {citation.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default CitationList;
