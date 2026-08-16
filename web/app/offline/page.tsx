import copy from '@/lib/copy/en-IN';

/** Service-worker fallback for a route that was never cached. */
export default function OfflinePage() {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
        {copy.offline.pageHeading}
      </h1>
      <p className="m-0 max-w-prose text-sm text-[var(--color-text-secondary)]">
        {copy.offline.pageBody}
      </p>
      <a href="/" className="text-sm underline underline-offset-2">
        {copy.nav.today}
      </a>
    </div>
  );
}
