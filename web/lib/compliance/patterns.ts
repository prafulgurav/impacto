/**
 * Compliance guardrail, ported from src/impacto/explain/guardrails.py.
 *
 * The Python guardrail protects generated text. It does not protect the copy this
 * UI ships, so the same rules are enforced again here — over lib/copy/en-IN.ts and
 * over the static content of /methodology and /compliance — as a build-blocking
 * test.
 *
 * Both implementations are judged by one shared fixture (lib/compliance-fixtures.json,
 * at the repo root) exercised from pytest and vitest alike. Two copies of a regex
 * set drift apart otherwise, and the drift is silent.
 *
 * Note the deliberate narrowness of the trade-verb rules. A naive /\b(buy|sell)\b/
 * blocklist is what most teams ship and it is useless here: the transmission map
 * legitimately contains sentences like "low foreign ownership means there is little
 * to sell". Blocking those would either break the product or train the team to
 * disable the guardrail. So trade verbs are only flagged in an advisory context —
 * sentence-initial imperative, or governed by a recommendation verb.
 */

const TRADE_VERB =
  '(?:buy|sell|short|accumulate|offload|exit|book\\s+profits?|square\\s+off)';

/** Imperatives to transact. Never exempted, not even in a historical sentence. */
export const ACTION_PATTERNS: RegExp[] = [
  // Explicit recommendation framing.
  new RegExp(
    `\\b(?:you|investors?|traders?|one)\\s+(?:should|must|ought\\s+to|can)\\s+${TRADE_VERB}`,
    'i',
  ),
  /\b(?:we|i)\s+(?:recommend|suggest|advise)\b/i,
  /\badvise\s+(?:you|investors?|clients?)\s+to\b/i,
  /\bour\s+(?:advice|recommendation|call)\s+is\b/i,
  // Sentence-initial imperative: "Buy IT stocks." / "Book profits in metals now."
  new RegExp(`^${TRADE_VERB}\\b`, 'i'),
  // Analyst-style rating language.
  /\b(?:strong\s+)?(?:buy|sell|hold)\s+(?:rating|call|recommendation)\b/i,
  new RegExp(`\\b(?:time|right\\s+time)\\s+to\\s+${TRADE_VERB}`, 'i'),
  /\b(?:go\s+long|go\s+short)\b/i,
];

/** Forward-looking directional claims. */
export const FORECAST_PATTERNS: RegExp[] = [
  /\b(?:will|shall)\s+(?:likely\s+)?(?:rise|fall|drop|surge|crash|rally|decline|jump|plunge|gain|lose)\b/i,
  /\bis\s+(?:going\s+to|about\s+to)\s+(?:rise|fall|drop|surge|rally|decline)\b/i,
  /\b(?:expect|anticipate|forecast|predict|project)(?:s|ed|ing)?\s+(?:a\s+|an\s+|the\s+)?(?:\w+\s+){0,3}(?:to\s+)?(?:rise|fall|drop|surge|rally|decline|gain|lose|move)\b/i,
  /\b(?:price\s+)?target\s+(?:of\s+)?(?:rs\.?|₹|inr)\s*[\d,]+/i,
  /\b(?:upside|downside)\s+of\s+\d+\s*%/i,
  /\bguaranteed\s+(?:returns?|profits?)\b/i,
  /\b(?:multibagger|sure\s+shot|can't\s+lose|risk[-\s]free\s+returns?)\b/i,
];

/**
 * Phrases that make an otherwise forward-looking sentence a statement of fact.
 * "NIFTY IT historically fell 180 bps" is history, not a prediction.
 */
export const HISTORICAL_MARKERS =
  /\b(?:historic(?:al|ally)|in the past|previously|past occurrences?|observed|realised|realized|median|mean|average|sample|backtest|event stud(?:y|ies)|has\s+(?:historically\s+)?(?:moved|fallen|risen))\b/i;

export interface ComplianceFlag {
  readonly sentence: string;
  readonly kind: 'action_language' | 'forward_looking';
  readonly pattern: string;
}

export interface ComplianceResult {
  readonly passed: boolean;
  readonly flags: readonly ComplianceFlag[];
}

/** Split on sentence terminators, matching the Python implementation. */
export function sentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Scan text for advice-like or forward-looking language.
 *
 * Sentences carrying an explicit historical marker are exempt from the forecast
 * check. Action imperatives are never exempt.
 */
export function checkText(text: string): ComplianceResult {
  const flags: ComplianceFlag[] = [];

  for (const sentence of sentences(text)) {
    for (const rx of ACTION_PATTERNS) {
      if (rx.test(sentence)) {
        flags.push({
          sentence,
          kind: 'action_language',
          pattern: rx.source.slice(0, 60),
        });
      }
    }
    if (!HISTORICAL_MARKERS.test(sentence)) {
      for (const rx of FORECAST_PATTERNS) {
        if (rx.test(sentence)) {
          flags.push({
            sentence,
            kind: 'forward_looking',
            pattern: rx.source.slice(0, 60),
          });
        }
      }
    }
  }

  return { passed: flags.length === 0, flags };
}

/** Walk an object tree and check every string it contains. */
export function checkStrings(
  value: unknown,
  path: string[] = [],
): { path: string; result: ComplianceResult }[] {
  if (typeof value === 'string') {
    const result = checkText(value);
    return result.passed ? [] : [{ path: path.join('.'), result }];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item, i) => checkStrings(item, [...path, String(i)]));
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, item]) =>
      // Keys prefixed with _ are notes to maintainers, not user-facing copy.
      key.startsWith('_') ? [] : checkStrings(item, [...path, key]),
    );
  }
  return [];
}
