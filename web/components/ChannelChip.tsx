'use client';
// 'use client': tap-to-expand needs local state.

import { useState } from 'react';

import copy from '@/lib/copy/en-IN';
import type { Channel } from '@/lib/api/client';

/**
 * A transmission channel, with its mechanism one tap away.
 *
 * The mechanism is the product. Showing a channel name alone would reduce the
 * map to a set of labels, which is exactly the correlation-without-explanation
 * that this engine exists to avoid.
 */
export function ChannelChip({ channel }: { channel: Channel }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="inline-flex flex-col">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-1)] px-2.5 py-1 text-xs text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-baseline)]"
      >
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 rounded-full bg-[var(--color-baseline)]"
        />
        {channel.name}
        <span className="text-[10px] text-[var(--color-muted)]">
          {channel.horizon}
        </span>
        <span className="sr-only">
          {open ? copy.a11y.collapse : copy.a11y.expand}
        </span>
      </button>
      {open && (
        <p className="mt-1.5 max-w-prose rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2 text-xs leading-relaxed text-[var(--color-text-secondary)]">
          {channel.description}
        </p>
      )}
    </div>
  );
}

export default ChannelChip;
