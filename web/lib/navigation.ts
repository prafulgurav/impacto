import copy from '@/lib/copy/en-IN';

/**
 * Route metadata, in a plain module.
 *
 * Deliberately not exported from the 'use client' navigation component: values
 * crossing that boundary into a Server Component arrive as proxies, not arrays,
 * and the failure is a runtime error during prerender rather than a type error.
 */

/** Five tabs maximum — a sixth makes every tab smaller. */
export const TABS = [
  { href: '/', label: copy.nav.today, icon: '◐' },
  { href: '/explore', label: copy.nav.explore, icon: '⊞' },
  { href: '/ask', label: copy.nav.ask, icon: '?' },
  { href: '/portfolio', label: copy.nav.portfolio, icon: '◧' },
  { href: '/more', label: copy.nav.more, icon: '⋯' },
] as const;

/** Destinations people arrive at deliberately, so they live under More. */
export const MORE_LINKS = [
  { href: '/calibration', label: copy.nav.calibration },
  { href: '/methodology', label: copy.nav.methodology },
  { href: '/compliance', label: copy.nav.compliance },
  { href: '/settings', label: copy.nav.settings },
] as const;

export function isActive(pathname: string, href: string): boolean {
  return href === '/' ? pathname === '/' : pathname.startsWith(href);
}
