/**
 * The highest-leverage test in the repo.
 *
 * Two things happen here:
 *  1. the TypeScript guardrail is judged by the SAME fixture that judges the
 *     Python one (lib/compliance-fixtures.json at the repo root), so the two
 *     implementations cannot drift apart silently;
 *  2. every string the UI ships is scanned, and a violation fails the build.
 */
import { describe, expect, it } from 'vitest';

import fixtures from '../../../lib/compliance-fixtures.json';
import {
  ACTION_PATTERNS,
  FORECAST_PATTERNS,
  checkStrings,
  checkText,
  sentences,
} from '@/lib/compliance/patterns';
import copy from '@/lib/copy/en-IN';

describe('shared fixture — the same cases the Python guardrail is held to', () => {
  it.each(fixtures.blocked.map((c) => [c.text, c.why] as const))(
    'blocks %j (%s)',
    (text) => {
      expect(checkText(text).passed).toBe(false);
    },
  );

  it.each(fixtures.allowed.map((c) => [c.text, c.why] as const))(
    'allows %j (%s)',
    (text) => {
      const result = checkText(text);
      expect(
        result.passed,
        `unexpectedly flagged: ${JSON.stringify(result.flags)}`,
      ).toBe(true);
    },
  );

  it('has enough cases on both sides to be meaningful', () => {
    expect(fixtures.blocked.length).toBeGreaterThanOrEqual(10);
    expect(fixtures.allowed.length).toBeGreaterThanOrEqual(10);
  });
});

describe('pattern behaviour', () => {
  it('exempts a historical sentence from the forecast check', () => {
    // The same clause, with and without the historical marker.
    expect(checkText('NIFTY IT will fall.').passed).toBe(false);
    expect(checkText('NIFTY IT has historically fallen.').passed).toBe(true);
  });

  it('never exempts an action imperative, even in a historical sentence', () => {
    expect(
      checkText('Historically this worked. Buy IT stocks now.').passed,
    ).toBe(false);
  });

  it('does not flag a trade verb used descriptively', () => {
    expect(
      checkText('Low foreign ownership means there is little to sell.').passed,
    ).toBe(true);
  });

  it('splits sentences the way the Python implementation does', () => {
    expect(sentences('One. Two! Three?')).toEqual(['One.', 'Two!', 'Three?']);
  });

  it('reports which pattern family matched', () => {
    expect(checkText('Buy IT stocks.').flags[0]?.kind).toBe('action_language');
    expect(checkText('Infosys will surge.').flags[0]?.kind).toBe('forward_looking');
  });

  it('keeps both pattern sets non-empty', () => {
    expect(ACTION_PATTERNS.length).toBeGreaterThan(4);
    expect(FORECAST_PATTERNS.length).toBeGreaterThan(4);
  });
});

describe('shipped copy — build-blocking', () => {
  it('contains no compliance violation anywhere in en-IN.ts', () => {
    const violations = checkStrings(copy);
    expect(
      violations,
      violations
        .map((v) => `${v.path}: ${v.result.flags.map((f) => f.sentence).join(' | ')}`)
        .join('\n'),
    ).toEqual([]);
  });

  it('scans the static page content, not only the labels', () => {
    // /methodology and /compliance render entirely from these keys, so covering
    // them here covers those pages.
    for (const section of [copy.methodology, copy.compliance, copy.disclaimer]) {
      expect(checkStrings(section)).toEqual([]);
    }
  });

  it('keeps the portfolio screen free of action language', () => {
    const banned = [
      'consider',
      'you may want to',
      'you should',
      'recommend',
      'opportunity',
    ];
    const text = JSON.stringify(copy.portfolio).toLowerCase();
    for (const phrase of banned) {
      expect(text, `portfolio copy contains "${phrase}"`).not.toContain(phrase);
    }
  });

  it('ships a disclaimer that names the regulator and denies prediction', () => {
    expect(copy.disclaimer.full).toContain('SEBI');
    expect(copy.disclaimer.full).toContain('not investment advice');
    expect(copy.disclaimer.full).toContain('do not predict future returns');
  });

  it('states the AI disclosure on the ask screen and the compliance page', () => {
    expect(copy.ask.aiDisclosure).toMatch(/cannot introduce a number/i);
    expect(copy.compliance.aiBody).toMatch(/cannot introduce a figure/i);
  });

  it('never puts a number in the push notification copy', () => {
    // A stale figure on a lock screen is the exact failure this prevents.
    expect(copy.notifications.contentNote).toMatch(/never carries a number/i);
  });
});

describe('a planted violation is caught', () => {
  it('fails the scan when advice language is introduced', () => {
    // Stands in for the deliberate plant-and-remove exercise: this is what the
    // build sees if someone adds a line like this to the copy file.
    const planted = { ...copy, today: { ...copy.today, empty: 'Buy IT stocks now.' } };
    const violations = checkStrings(planted);
    expect(violations).toHaveLength(1);
    expect(violations[0]?.path).toBe('today.empty');
    expect(violations[0]?.result.flags[0]?.kind).toBe('action_language');
  });

  it('fails the scan when a forward-looking claim is introduced', () => {
    const planted = {
      ...copy,
      today: { ...copy.today, empty: 'NIFTY Bank will drop tomorrow.' },
    };
    expect(checkStrings(planted)[0]?.result.flags[0]?.kind).toBe('forward_looking');
  });
});
