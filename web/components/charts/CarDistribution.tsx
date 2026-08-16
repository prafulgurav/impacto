'use client';
// 'use client': the histogram/strip-plot switch is measured from container width.

import { useEffect, useMemo, useRef, useState } from 'react';

import copy from '@/lib/copy/en-IN';
import { bps, formatDate, realisedTone } from '@/lib/format';

/**
 * Histogram of realised cumulative abnormal returns, with a median rule and a
 * zero reference. Custom SVG.
 *
 * Below 480px this becomes a horizontal strip plot — one dot per past occurrence.
 * Histograms need width to be readable, and a strip plot shows the same sample
 * honestly at any size, including how few observations there usually are.
 */

export interface CarDistributionPoint {
  eventId: string;
  eventDate: string;
  headline: string;
  carBps: number;
}

export interface CarDistributionProps {
  points: CarDistributionPoint[];
  medianBps: number;
  forceCompact?: boolean;
}

const BREAKPOINT = 480;
const TONE_VAR = {
  pos: 'var(--color-pos)',
  neg: 'var(--color-neg)',
  neutral: 'var(--color-neutral)',
} as const;

function buildBins(points: CarDistributionPoint[], binCount: number) {
  const values = points.map((p) => p.carBps);
  const max = Math.max(...values.map(Math.abs), 100);
  // Symmetric around zero so the eye reads direction, not binning artefacts.
  const bound = Math.ceil(max / 50) * 50;
  const width = (bound * 2) / binCount;
  const bins = Array.from({ length: binCount }, (_, i) => ({
    lo: -bound + i * width,
    hi: -bound + (i + 1) * width,
    count: 0,
  }));
  for (const value of values) {
    const index = Math.min(
      binCount - 1,
      Math.max(0, Math.floor((value + bound) / width)),
    );
    bins[index]!.count += 1;
  }
  return { bins, bound };
}

export function CarDistribution({
  points,
  medianBps,
  forceCompact = false,
}: CarDistributionProps) {
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

  const binCount = points.length > 20 ? 13 : 9;
  const { bins, bound } = useMemo(
    () => buildBins(points.length ? points : [], binCount),
    [points, binCount],
  );

  if (points.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">{copy.charts.noData}</p>
    );
  }

  return (
    <div ref={containerRef} className="w-full">
      <figure className="m-0">
        <figcaption className="mb-2 text-[11px] uppercase tracking-[0.06em] text-[var(--color-muted)]">
          {copy.charts.distributionTitle}
        </figcaption>

        {compact ? (
          <StripPlot points={points} medianBps={medianBps} bound={bound} />
        ) : (
          <Histogram bins={bins} bound={bound} medianBps={medianBps} />
        )}

        <p className="mt-2 text-[11px] text-[var(--color-muted)]">
          {copy.charts.axisCar}
          {compact ? ` · ${copy.charts.stripPlotHint}` : ''}
        </p>
      </figure>
    </div>
  );
}

function Histogram({
  bins,
  bound,
  medianBps,
}: {
  bins: { lo: number; hi: number; count: number }[];
  bound: number;
  medianBps: number;
}) {
  const width = 620;
  const height = 200;
  const padBottom = 26;
  const plotHeight = height - padBottom;
  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  const scaleX = (v: number) => ((v + bound) / (2 * bound)) * width;
  const barWidth = width / bins.length;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      role="img"
      aria-label={copy.a11y.chartDescription}
    >
      {[-bound, -bound / 2, 0, bound / 2, bound].map((tick) => (
        <g key={tick}>
          <line
            x1={scaleX(tick)}
            x2={scaleX(tick)}
            y1={0}
            y2={plotHeight}
            stroke={tick === 0 ? 'var(--color-baseline)' : 'var(--color-grid)'}
            strokeWidth={tick === 0 ? 2 : 1}
          />
          <text
            x={scaleX(tick)}
            y={height - 8}
            textAnchor="middle"
            className="tnum"
            fontSize={10}
            fill="var(--color-muted)"
          >
            {bps(tick)}
          </text>
        </g>
      ))}

      {bins.map((bin) => {
        const barHeight = (bin.count / maxCount) * (plotHeight - 8);
        const mid = (bin.lo + bin.hi) / 2;
        return (
          <rect
            key={bin.lo}
            x={scaleX(bin.lo) + 1}
            y={plotHeight - barHeight}
            width={Math.max(1, barWidth - 2)}
            height={barHeight}
            rx={4}
            fill={TONE_VAR[realisedTone(mid)]}
            opacity={0.75}
          />
        );
      })}

      {/* Median rule, drawn over the bars so it is never lost among them. */}
      <line
        x1={scaleX(medianBps)}
        x2={scaleX(medianBps)}
        y1={0}
        y2={plotHeight}
        stroke="var(--color-text-primary)"
        strokeWidth={2}
        strokeDasharray="4 3"
      />
      <text
        x={scaleX(medianBps)}
        y={12}
        textAnchor="middle"
        fontSize={10}
        fill="var(--color-text-primary)"
      >
        {copy.charts.distributionMedianRule} {bps(medianBps)}
      </text>
    </svg>
  );
}

function StripPlot({
  points,
  medianBps,
  bound,
}: {
  points: CarDistributionPoint[];
  medianBps: number;
  bound: number;
}) {
  const width = 340;
  const height = 96;
  const axisY = 52;
  const scaleX = (v: number) => ((v + bound) / (2 * bound)) * (width - 16) + 8;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      role="img"
      aria-label={copy.a11y.chartDescription}
    >
      <line
        x1={8}
        x2={width - 8}
        y1={axisY}
        y2={axisY}
        stroke="var(--color-grid)"
        strokeWidth={1}
      />
      <line
        x1={scaleX(0)}
        x2={scaleX(0)}
        y1={axisY - 22}
        y2={axisY + 22}
        stroke="var(--color-baseline)"
        strokeWidth={2}
      />

      {points.map((point, index) => (
        <circle
          key={point.eventId}
          cx={scaleX(point.carBps)}
          // Slight vertical jitter so overlapping observations stay countable.
          cy={axisY + ((index % 3) - 1) * 7}
          r={4}
          fill={TONE_VAR[realisedTone(point.carBps)]}
          stroke="var(--color-surface-1)"
          strokeWidth={2}
        >
          <title>
            {formatDate(point.eventDate)}: {bps(point.carBps)} bps
          </title>
        </circle>
      ))}

      <line
        x1={scaleX(medianBps)}
        x2={scaleX(medianBps)}
        y1={axisY - 26}
        y2={axisY + 26}
        stroke="var(--color-text-primary)"
        strokeWidth={2}
        strokeDasharray="4 3"
      />
      <text
        x={scaleX(medianBps)}
        y={axisY + 40}
        textAnchor="middle"
        fontSize={10}
        fill="var(--color-text-primary)"
      >
        {copy.charts.distributionMedianRule} {bps(medianBps)}
      </text>
      {[-bound, 0, bound].map((tick) => (
        <text
          key={tick}
          x={scaleX(tick)}
          y={14}
          textAnchor="middle"
          className="tnum"
          fontSize={9}
          fill="var(--color-muted)"
        >
          {bps(tick)}
        </text>
      ))}
    </svg>
  );
}

export default CarDistribution;
