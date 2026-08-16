import Link from 'next/link';

import copy from '@/lib/copy/en-IN';

export default function NotFound() {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
        {copy.errors.notFound}
      </h1>
      <p className="m-0 text-sm text-[var(--color-text-secondary)]">
        {copy.errors.notFoundBody}
      </p>
      <Link href="/" className="text-sm underline underline-offset-2">
        {copy.nav.today}
      </Link>
    </div>
  );
}
