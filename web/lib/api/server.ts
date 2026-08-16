/**
 * Server-side data access for the statically generated routes.
 *
 * These run at build time and on ISR revalidation, so they talk to the API
 * directly rather than through the browser's /api proxy. A fetch failure returns
 * null instead of throwing: a build must not fail because one archetype's
 * statistics were briefly unavailable, and the page renders its no-sample state.
 */

import type {
  AnalogSummary,
  ArchetypeDetail,
  CalibrationReport,
  Channel,
} from './client';

const SERVER_API =
  process.env.API_ORIGIN ??
  process.env.NEXT_PUBLIC_API_ORIGIN ??
  'http://localhost:8000';

/** ISR window. The precompute job runs nightly, so a day is the natural period. */
export const REVALIDATE_SECONDS = 60 * 60 * 24;

async function get<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${SERVER_API}${path}`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export interface ArchetypeSummary {
  id: string;
  label: string;
  family: string;
  description: string;
  n_impacts: number;
  targets: string[];
}

export const serverApi = {
  archetypes: () => get<ArchetypeSummary[]>('/knowledge/archetypes'),
  archetype: (id: string) =>
    get<ArchetypeDetail>(`/knowledge/archetypes/${encodeURIComponent(id)}`),
  channels: () => get<Channel[]>('/knowledge/channels'),
  analogs: (archetypeId: string, target: string, window?: string) =>
    get<AnalogSummary>(
      `/analogs?archetype_id=${encodeURIComponent(archetypeId)}&target=${encodeURIComponent(target)}` +
        (window ? `&window=${encodeURIComponent(window)}` : ''),
    ),
  calibration: (window?: string) =>
    get<CalibrationReport>(
      `/calibration${window ? `?window=${encodeURIComponent(window)}` : ''}`,
    ),
};
