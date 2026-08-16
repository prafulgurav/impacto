'use client';
// 'use client': the layout switches on a container-width media query, which
// needs a resize observer.

import { useEffect, useRef, useState } from 'react';

import EvidenceBadge from '@/components/EvidenceBadge';
import copy from '@/lib/copy/en-IN';
import { bps, directionTone, realisedTone } from '@/lib/format';

/**
 * Diverging horizontal bars. Custom SVG, not a chart library.
 *
 * The encoding carries two different kinds of claim and must keep them distinct:
 *   bar  = the range encoded in the transmission map — a hypothesis
 *   dot  = the median that was actually realised — a measurement
 *
 * Below 480px this degrades to a list with an inline mini-bar per row rather than
 * shrinking. A five-series diverging chart at 360px is unreadable, and a chart
 * nobody can read is worse than a table.
 */

export interface ImpactBarRow {
  target: string;
  label: string;
  direction: -1 | 0 | 1;
  priorLowBps: number;
  priorHighBps: number;
  realisedMedianBps: number | null;
  sampleSize: number;
  pValue: number;
}

export interface ImpactBarsProps {
  rows: ImpactBarRow[];
  /** Forces the compact layout; used by tests and visual baselines. */
  forceCompact?: boolean;
}

const BREAKPOINT = 480;
const BAR_HEIGHT = 20; // <= 24px per the mark spec
const ROW_GAP = 10; // leaves a 2px surface gap between adjacent bars
const LABEL_WIDTH = 116;
const MARKER_RADIUS = 5; // >= 8px diameter

const TONE_VAR = {
  pos: 'var(--color-pos)',
  neg: 'var(--color-neg)',
  neutral: 'var(--color-neutral)',
} as const;

function niceBound(rows: ImpactBarRow[]): number {
  const extremes = rows.flatMap((r) => [
    Math.abs(r.priorLowBps),
    Math.abs(r.priorHighBps),
    r.realisedMedianBps === null ? 0 : Math.abs(r.realisedMedianBps),
  ]);
  const max = Math.max(100, ...extremes);
  // Round out to a readable gridline rather than a value derived from the data.
  const step = max > 800 ? 250 : max > 300 ? 100 : 50;
  return Math.ceil(max / step) * step;
}

export function ImpactBars({ rows, forceCompact = false }: ImpactBarsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(forceCompact);

  useEffect(() => {
    if (forceCompact) return;
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setCompact(entry.contentRect.width < BREAKPOINT);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [forceCompact]);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">{copy.charts.noData}</p>
    );
  }

  const bound = niceBound(rows);

  return (
    <div ref={containerRef} className="w-full">
      <figure className="m-0">
        <figcaption className="mb-2 text-[11px] uppercase tracking-[0.06em] text-[var(--color-muted)]">
          {copy.charts.impactBarsTitle}
        </figcaption>

        {compact ? (
          <CompactList rows={rows} bound={bound} />
        ) : (
          <WideChart rows={rows} bound={bound} />
        )}

        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--color-muted)]">
          <span>{copy.charts.impactBarsLegendBar}</span>
          <span>{copy.charts.impactBarsLegendDot}</span>
        </div>
      </figure>
    </div>
  );
}

function WideChart({ rows, bound }: { rows: ImpactBarRow[]; bound: number }) {
  const width = 620;
  const height = rows.length * (BAR_HEIGHT + ROW_GAP) + 26;
  const plotLeft = LABEL_WIDTH;
  const plotWidth = width - plotLeft - 16;
  const centre = plotLeft + plotWidth / 2;
  const scale = (value: number) => centre + (value / bound) * (plotWidth / 2);

  const ticks = [-bound, -bound / 2, 0, bound / 2, bound];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      role="img"
      aria-label={copy.a11y.chartDescription}
      style={{ overflow: 'visible' }}
    >
      {/* Hairline solid gridlines. */}
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={scale(tick)}
            x2={scale(tick)}
            y1={0}
            y2={height - 22}
            stroke={tick === 0 ? 'var(--color-baseline)' : 'var(--color-grid)'}
            strokeWidth={tick === 0 ? 2 : 1}
          />
          <text
            x={scale(tick)}
            y={height - 6}
            textAnchor="middle"
            className="tnum"
            fontSize={10}
            fill="var(--color-muted)"
          >
            {bps(tick)}
          </text>
        </g>
      ))}

      {rows.map((row, index) => {
        const y = index * (BAR_HEIGHT + ROW_GAP);
        const tone = TONE_VAR[directionTone(row.direction)];
        const x1 = scale(Math.min(row.priorLowBps, row.priorHighBps));
        const x2 = scale(Math.max(row.priorLowBps, row.priorHighBps));

        return (
          <g key={row.target}>
            {/* Text never wears the series colour — identity comes from the
                mark beside it. */}
            <text
              x={plotLeft - 10}
              y={y + BAR_HEIGHT / 2 + 4}
              textAnchor="end"
              fontSize={12}
              fill="var(--color-text-primary)"
            >
              {row.label}
            </text>
            <rect
              x={x1}
              y={y}
              width={Math.max(2, x2 - x1)}
              height={BAR_HEIGHT}
              rx={4}
              fill={tone}
              opacity={row.direction === 0 ? 1 : 0.55}
            />
            {row.realisedMedianBps !== null && (
              <circle
                cx={scale(row.realisedMedianBps)}
                cy={y + BAR_HEIGHT / 2}
                r={MARKER_RADIUS}
                fill={TONE_VAR[realisedTone(row.realisedMedianBps)]}
                // 2px surface ring keeps the dot legible over its own bar.
                stroke="var(--color-surface-1)"
                strokeWidth={2}
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

/**
 * The sub-480px fallback: one row per target, each with an inline mini-bar.
 * Same information, laid out for a thumb rather than a mouse.
 */
function CompactList({ rows, bound }: { rows: ImpactBarRow[]; bound: number }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {rows.map((row) => {
        const tone = TONE_VAR[directionTone(row.direction)];
        const lo = Math.min(row.priorLowBps, row.priorHighBps);
        const hi = Math.max(row.priorLowBps, row.priorHighBps);
        const toPct = (v: number) => ((v + bound) / (2 * bound)) * 100;

        return (
          <li
            key={row.target}
            className="flex flex-col gap-1.5 border-b border-[var(--color-border)] pb-3 last:border-b-0"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium">{row.label}</span>
              {row.realisedMedianBps !== null && (
                <EvidenceBadge
                  sampleSize={row.sampleSize}
                  pValue={row.pValue}
                >
                  <span
                    className="pnum text-sm font-semibold"
                    style={{ color: TONE_VAR[realisedTone(row.realisedMedianBps)] }}
                  >
                    {bps(row.realisedMedianBps)} {copy.evidence.unitBps}
                  </span>
                </EvidenceBadge>
              )}
            </div>

            <div
              className="relative h-2.5 w-full rounded-full bg-[var(--color-grid)]"
              role="presentation"
            >
              {/* zero reference */}
              <span
                className="absolute top-[-2px] h-[14px] w-0.5 bg-[var(--color-baseline)]"
                style={{ left: '50%' }}
              />
              <span
                className="absolute inset-y-0 rounded-full"
                style={{
                  left: `${toPct(lo)}%`,
                  width: `${Math.max(2, toPct(hi) - toPct(lo))}%`,
                  background: tone,
                  opacity: row.direction === 0 ? 1 : 0.55,
                }}
              />
              {row.realisedMedianBps !== null && (
                <span
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[var(--color-surface-1)]"
                  style={{
                    left: `${toPct(row.realisedMedianBps)}%`,
                    background: TONE_VAR[realisedTone(row.realisedMedianBps)],
                  }}
                />
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default ImpactBars;
