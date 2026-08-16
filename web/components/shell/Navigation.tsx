'use client';
// 'use client': highlights the active route from usePathname.

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import copy from '@/lib/copy/en-IN';
import { MORE_LINKS, TABS, isActive } from '@/lib/navigation';

/**
 * Bottom tab bar on mobile (thumb reach), sidebar at >=1024px.
 */
export function BottomTabBar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label={copy.nav.today}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--color-border)] bg-[var(--color-surface-1)]/95 backdrop-blur lg:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className="m-0 flex list-none items-stretch justify-around p-0">
        {TABS.map((tab) => {
          const active = isActive(pathname, tab.href);
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                aria-current={active ? 'page' : undefined}
                className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 text-[11px] ${
                  active
                    ? 'text-[var(--color-text-primary)]'
                    : 'text-[var(--color-muted)]'
                }`}
              >
                <span aria-hidden="true" className="text-base leading-none">
                  {tab.icon}
                </span>
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label={copy.nav.more}
      className="hidden w-56 shrink-0 flex-col gap-1 border-r border-[var(--color-border)] px-3 py-6 lg:flex"
    >
      <span className="px-3 pb-3 text-sm font-semibold tracking-[-0.01em]">
        {copy.app.name}
      </span>
      {[...TABS.filter((t) => t.href !== '/more'), ...MORE_LINKS].map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={`rounded-lg px-3 py-2 text-sm transition-colors ${
              active
                ? 'bg-[var(--color-plane)] font-medium text-[var(--color-text-primary)]'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-plane)]'
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

