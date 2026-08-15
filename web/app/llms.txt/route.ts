import { serverApi } from '@/lib/api/server';

/**
 * llms.txt — how LLM search surfaces find and cite these pages.
 *
 * One line per archetype with a one-line description, so an assistant answering
 * "how do Fed rate hikes affect Indian IT stocks" can find the page that has the
 * measured answer rather than paraphrasing a blog post.
 */
export const revalidate = 86_400;

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://impacto.app';

export async function GET(): Promise<Response> {
  const archetypes = (await serverApi.archetypes()) ?? [];

  const body = [
    '# Impacto',
    '',
    '> Historical statistics on how global events have moved Indian equity sectors.',
    "> Each archetype page reports what actually happened after past occurrences —",
    '> median cumulative abnormal return, sample size and p-value — computed with a',
    '> market-model event study. Not investment advice; no forward-looking claims.',
    '',
    '## Event archetypes',
    '',
    ...archetypes.map(
      (a) => `- [${a.label}](${SITE}/explore/${a.id}): ${a.description.split('.')[0]}.`,
    ),
    '',
    '## Reference',
    '',
    `- [Calibration](${SITE}/calibration): every encoded prior scored against realised history.`,
    `- [Methodology](${SITE}/methodology): how cumulative abnormal returns are computed.`,
    `- [Compliance](${SITE}/compliance): regulatory position, AI disclosure and data sources.`,
    '',
  ].join('\n');

  return new Response(body, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=86400',
    },
  });
}
