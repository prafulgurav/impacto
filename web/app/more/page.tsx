import Link from 'next/link';

import ThemeToggle from '@/components/shell/ThemeToggle';
import copy from '@/lib/copy/en-IN';
import { MORE_LINKS } from '@/lib/navigation';

/** The fifth tab. Everything that is a destination rather than a daily surface. */
export default function MorePage() {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
        {copy.nav.more}
      </h1>
      <nav>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {MORE_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="block rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2.5 text-sm"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <section>
        <h2 className="m-0 mb-2 text-sm font-semibold">
          {copy.settings.themeHeading}
        </h2>
        <ThemeToggle />
      </section>
    </div>
  );
}
