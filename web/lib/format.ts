/**
 * Formatters. Every number a user sees passes through one of these.
 *
 * The rule these encode: a figure is never shown with more precision than the
 * sample supports. A median of 12 observations does not get two decimal places.
 */

/** Basis points, always signed, always whole. */
export function bps(value: number): string {
  const rounded = Math.round(value);
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : '';
  return `${sign}${Math.abs(rounded).toLocaleString('en-IN')}`;
}

/** Basis points with the unit attached. */
export function bpsWithUnit(value: number): string {
  return `${bps(value)} bps`;
}

/**
 * p-values. Below 0.001 the exact figure is noise, so it is reported as a bound.
 */
export function pValue(value: number): string {
  if (value < 0.001) return '<0.001';
  return value.toFixed(3);
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** Above this threshold the distribution is not distinguishable from noise. */
export const NOISE_THRESHOLD = 0.1;

export function isNoise(p: number): boolean {
  return p > NOISE_THRESHOLD;
}

const DATE_FMT = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'Asia/Kolkata',
});

const DATE_TIME_FMT = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'Asia/Kolkata',
});

export function formatDate(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  return Number.isNaN(date.getTime()) ? '—' : DATE_FMT.format(date);
}

/**
 * Data age, for the offline banner. Deliberately shows the timestamp rather than
 * only a connection state: "you're offline" does not tell a user whether what
 * they are looking at is two minutes or two weeks old.
 */
export function formatDataAge(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  return Number.isNaN(date.getTime()) ? '—' : DATE_TIME_FMT.format(date);
}

export function titleCase(value: string): string {
  return value
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Direction as a token name; never resolves a two-sided prior to a sign. */
export function directionTone(direction: -1 | 0 | 1): 'pos' | 'neg' | 'neutral' {
  if (direction > 0) return 'pos';
  if (direction < 0) return 'neg';
  return 'neutral';
}

/** The tone of a *realised* median, which is a fact rather than a claim. */
export function realisedTone(median: number): 'pos' | 'neg' | 'neutral' {
  if (median > 0) return 'pos';
  if (median < 0) return 'neg';
  return 'neutral';
}
