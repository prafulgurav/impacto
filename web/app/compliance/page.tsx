import type { Metadata } from 'next';

import copy from '@/lib/copy/en-IN';

export const metadata: Metadata = {
  title: copy.nav.compliance,
  description: copy.compliance.sebiBody,
  alternates: { canonical: '/compliance' },
};

/**
 * The SEBI position, what this is and is not, the AI disclosure, and the data
 * sources. Static, and every string lives in the copy file so the build-blocking
 * compliance scan covers this page too.
 */
export default function CompliancePage() {
  const sections = [
    { heading: copy.compliance.sebiHeading, body: copy.compliance.sebiBody },
    { heading: copy.compliance.isHeading, body: copy.compliance.isBody },
    { heading: copy.compliance.isNotHeading, body: copy.compliance.isNotBody },
    { heading: copy.compliance.aiHeading, body: copy.compliance.aiBody },
    { heading: copy.compliance.sourcesHeading, body: copy.compliance.sourcesBody },
    { heading: copy.compliance.contactHeading, body: copy.compliance.contactBody },
  ];

  return (
    <article className="flex flex-col gap-5">
      <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
        {copy.compliance.title}
      </h1>

      <p className="m-0 max-w-prose rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3 text-sm leading-relaxed">
        {copy.disclaimer.full}
      </p>

      {sections.map((section) => (
        <section key={section.heading}>
          <h2 className="m-0 mb-1 text-sm font-semibold">{section.heading}</h2>
          <p className="m-0 max-w-prose text-sm leading-relaxed text-[var(--color-text-secondary)]">
            {section.body}
          </p>
        </section>
      ))}
    </article>
  );
}
