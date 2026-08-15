import type { Metadata } from 'next';

import copy from '@/lib/copy/en-IN';

export const metadata: Metadata = {
  title: copy.nav.methodology,
  description: copy.methodology.body,
  alternates: { canonical: '/methodology' },
};

/** Static. All content comes from the copy file, so the compliance scan sees it. */
export default function MethodologyPage() {
  const sections = [
    { heading: copy.methodology.heading, body: copy.methodology.body },
    { heading: copy.methodology.windowsHeading, body: copy.methodology.windowsBody },
    {
      heading: copy.methodology.distributionHeading,
      body: copy.methodology.distributionBody,
    },
    { heading: copy.methodology.limitsHeading, body: copy.methodology.limitsBody },
  ];

  return (
    <article className="flex flex-col gap-5">
      <h1 className="m-0 text-2xl font-semibold tracking-[-0.02em]">
        {copy.methodology.title}
      </h1>
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
