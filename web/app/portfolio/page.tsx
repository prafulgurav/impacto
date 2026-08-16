'use client';
// 'use client': holdings entry is a form with autocomplete and local state.

import { useEffect, useMemo, useState } from 'react';

import ChannelChip from '@/components/ChannelChip';
import copy from '@/lib/copy/en-IN';
import { ApiError, api } from '@/lib/api/client';
import type { Channel, Holding } from '@/lib/api/client';
import { percent, titleCase } from '@/lib/format';

/**
 * Exposure attribution.
 *
 * Read §6 of the build brief before changing a single string on this screen. It
 * says EXPOSURE and never ACTION: no "consider", no "you may want to", no
 * red/green profit framing, and no ranking that implies what to do. Describing
 * where a portfolio's weight sits is information; ordering those sectors by
 * attractiveness would be a recommendation.
 */

interface Exposure {
  sector: string;
  weight: number;
  archetypes: string[];
  channels: string[];
}

export default function PortfolioPage() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [authRequired, setAuthRequired] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [existing, channelList] = await Promise.all([
          api.holdings(),
          api.channels().catch(() => [] as Channel[]),
        ]);
        setHoldings(existing.holdings);
        setChannels(channelList);
      } catch (error) {
        if (error instanceof ApiError && error.kind === 'unauthorized') {
          setAuthRequired(true);
        }
      }
    })();

    // The universe is the source of truth for valid NSE symbols; the archetype
    // targets are what the engine can actually attribute exposure against.
    void api
      .archetypes()
      .then((list) => setSymbols([...new Set(list.flatMap((a) => a.targets))].sort()))
      .catch(() => undefined);
  }, []);

  const totalWeight = useMemo(
    () => holdings.reduce((sum, h) => sum + h.weight, 0),
    [holdings],
  );

  const exposures: Exposure[] = useMemo(
    () =>
      holdings
        .filter((h) => h.weight > 0)
        .map((h) => ({
          sector: h.symbol,
          weight: h.weight,
          archetypes: [],
          channels: [],
        })),
    [holdings],
  );

  async function save() {
    if (totalWeight > 1.0001) {
      setStatus('error');
      setMessage(copy.portfolio.weightsExceeded);
      return;
    }
    setStatus('saving');
    setMessage(null);
    try {
      const saved = await api.updateHoldings(holdings);
      setHoldings(saved.holdings);
      setStatus('saved');
      setMessage(copy.portfolio.saved);
    } catch (error) {
      if (error instanceof ApiError && error.kind === 'unauthorized') {
        setAuthRequired(true);
        setStatus('error');
        return;
      }
      // Offline or a transient failure: queue it and let the outbox replay.
      const { enqueue } = await import('@/lib/db/dexie');
      await enqueue('holdings', holdings);
      setStatus('saved');
      setMessage(copy.offline.queuedBody);
    }
  }

  if (authRequired) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
          {copy.portfolio.title}
        </h1>
        <p className="m-0 max-w-prose text-sm text-[var(--color-text-secondary)]">
          {copy.portfolio.signInRequired}
        </p>
        <a href="/settings" className="text-sm underline underline-offset-2">
          {copy.auth.signIn}
        </a>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
          {copy.portfolio.title}
        </h1>
        <p className="mt-1 max-w-prose text-sm text-[var(--color-text-secondary)]">
          {copy.portfolio.subtitle}
        </p>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          {copy.portfolio.privacy}
        </p>
      </header>

      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.portfolio.addHolding}
        </h2>

        <datalist id="nse-symbols">
          {symbols.map((symbol) => (
            <option key={symbol} value={symbol} />
          ))}
        </datalist>

        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {holdings.map((holding, index) => (
            <li key={index} className="flex items-end gap-2">
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <label
                  htmlFor={`symbol-${index}`}
                  className="text-[11px] uppercase tracking-[0.06em] text-[var(--color-muted)]"
                >
                  {copy.portfolio.symbolLabel}
                </label>
                <input
                  id={`symbol-${index}`}
                  list="nse-symbols"
                  value={holding.symbol}
                  placeholder={copy.portfolio.symbolPlaceholder}
                  onChange={(event) =>
                    setHoldings((prev) =>
                      prev.map((h, i) =>
                        i === index
                          ? { ...h, symbol: event.target.value.toUpperCase() }
                          : h,
                      ),
                    )
                  }
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-2.5 py-1.5 text-sm"
                />
              </div>
              <div className="flex w-28 flex-col gap-1">
                <label
                  htmlFor={`weight-${index}`}
                  className="text-[11px] uppercase tracking-[0.06em] text-[var(--color-muted)]"
                >
                  {copy.portfolio.weightLabel}
                </label>
                <input
                  id={`weight-${index}`}
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={holding.weight}
                  onChange={(event) =>
                    setHoldings((prev) =>
                      prev.map((h, i) =>
                        i === index
                          ? { ...h, weight: Number(event.target.value) }
                          : h,
                      ),
                    )
                  }
                  className="tnum rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-2.5 py-1.5 text-sm"
                />
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setHoldings((prev) => [...prev, { symbol: '', weight: 0 }])}
            className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm"
          >
            {copy.portfolio.addHolding}
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={status === 'saving' || holdings.length === 0}
            className="rounded-lg bg-[var(--color-text-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-surface-1)] disabled:opacity-40"
          >
            {copy.portfolio.save}
          </button>
          <span className="tnum text-xs text-[var(--color-muted)]">
            {percent(totalWeight)}
          </span>
        </div>

        {message && (
          <p role="status" className="m-0 mt-1.5 text-xs text-[var(--color-text-secondary)]">
            {message}
          </p>
        )}
      </section>

      {exposures.length > 0 ? (
        <section>
          <h2 className="m-0 mb-2 text-sm font-semibold">
            {copy.portfolio.exposureHeading}
          </h2>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {exposures.map((exposure) => (
              <li
                key={exposure.sector}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium">
                    {titleCase(exposure.sector)}
                  </span>
                  {/* Neutral weight bar, deliberately not tinted: a red or green
                      holdings row would read as a verdict on the position. */}
                  <span className="tnum text-sm text-[var(--color-text-secondary)]">
                    {percent(exposure.weight)}
                  </span>
                </div>
                <div
                  className="mt-1.5 h-1.5 w-full rounded-full bg-[var(--color-grid)]"
                  role="presentation"
                >
                  <span
                    className="block h-full rounded-full bg-[var(--color-baseline)]"
                    style={{ width: `${Math.min(100, exposure.weight * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section>
          <h2 className="m-0 mb-1 text-sm font-semibold">
            {copy.portfolio.emptyHeading}
          </h2>
          <p className="m-0 max-w-prose text-sm text-[var(--color-text-secondary)]">
            {copy.portfolio.emptyBody}
          </p>
        </section>
      )}

      {channels.length > 0 && (
        <section>
          <h2 className="m-0 mb-2 text-sm font-semibold">
            {copy.portfolio.channelsHeading}
          </h2>
          <div className="flex flex-wrap gap-2">
            {channels.slice(0, 6).map((channel) => (
              <ChannelChip key={channel.id} channel={channel} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
