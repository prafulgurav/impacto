/**
 * Typed fetch client.
 *
 * Three things it does that a bare fetch does not:
 *  - refreshes a stale access token once and retries, so a 15-minute token never
 *    surfaces as an error to a screen;
 *  - propagates a request id so a user-reported bug is traceable across tiers;
 *  - returns typed errors instead of throwing strings, so callers can distinguish
 *    "offline" from "rate limited" from "not signed in" and say the right thing.
 */

import type { paths } from '@/types/api';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '/api';

export type ApiErrorKind =
  | 'network'
  | 'offline'
  | 'unauthorized'
  | 'forbidden'
  | 'notFound'
  | 'rateLimited'
  | 'server'
  | 'unknown';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly requestId: string | null;
  readonly retryAfter: number | null;

  constructor(
    message: string,
    kind: ApiErrorKind,
    status = 0,
    requestId: string | null = null,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

function kindFor(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'notFound';
  if (status === 429) return 'rateLimited';
  if (status >= 500) return 'server';
  return 'unknown';
}

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/**
 * Exchange the refresh cookie for a new access token.
 *
 * De-duplicated: several screens can hit a 401 at the same moment, and firing one
 * refresh per screen would rotate the token repeatedly and invalidate itself.
 */
async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        accessToken = null;
        return false;
      }
      const body = (await response.json()) as { access_token: string };
      accessToken = body.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '');
  }
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Skip the refresh-and-retry dance (used by the auth calls themselves). */
  skipAuthRetry?: boolean;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, skipAuthRetry, headers, ...rest } = options;
  const requestId = newRequestId();

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    finalHeaders.set('X-Request-Id', requestId);
    if (body !== undefined) finalHeaders.set('Content-Type', 'application/json');
    if (accessToken) finalHeaders.set('Authorization', `Bearer ${accessToken}`);

    return fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: finalHeaders,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response: Response;
  try {
    response = await send();
  } catch (cause) {
    const offline =
      typeof navigator !== 'undefined' && navigator.onLine === false;
    throw new ApiError(
      offline ? 'offline' : 'network request failed',
      offline ? 'offline' : 'network',
      0,
      requestId,
    );
  }

  if (response.status === 401 && !skipAuthRetry && (await refreshAccessToken())) {
    response = await send();
  }

  if (!response.ok) {
    const retryAfter = response.headers.get('Retry-After');
    let detail = response.statusText;
    try {
      const parsed = (await response.json()) as { detail?: string };
      if (parsed.detail) detail = parsed.detail;
    } catch {
      // A non-JSON error body is fine; the status carries the meaning.
    }
    throw new ApiError(
      detail,
      kindFor(response.status),
      response.status,
      response.headers.get('X-Request-Id'),
      retryAfter ? Number(retryAfter) : null,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Endpoint paths, taken from the generated OpenAPI types where available. */
export type ApiPath = keyof paths;

export const api = {
  health: () => request<{ status: string; version: string }>('/health'),

  archetypes: () =>
    request<
      {
        id: string;
        label: string;
        family: string;
        description: string;
        n_impacts: number;
        targets: string[];
      }[]
    >('/knowledge/archetypes'),

  archetype: (id: string) => request<ArchetypeDetail>(`/knowledge/archetypes/${id}`),

  channels: () => request<Channel[]>('/knowledge/channels'),

  analogs: (archetypeId: string, target: string, window?: string) =>
    request<AnalogSummary>(
      `/analogs?archetype_id=${encodeURIComponent(archetypeId)}&target=${encodeURIComponent(target)}` +
        (window ? `&window=${encodeURIComponent(window)}` : ''),
    ),

  calibration: (window?: string) =>
    request<CalibrationReport>(
      `/calibration${window ? `?window=${encodeURIComponent(window)}` : ''}`,
    ),

  digest: () => request<Digest>('/digest'),

  alerts: () => request<Alert[]>('/alerts'),

  bundle: (etag?: string | null) =>
    request<OfflineBundle>('/bundle/offline', {
      headers: etag ? { 'If-None-Match': etag } : undefined,
    }),

  me: () => request<MeResponse>('/me'),

  updateWatchlist: (archetypeIds: string[], minSeverity: string) =>
    request<{ archetypeIds: string[]; minSeverity: string }>('/me/watchlist', {
      method: 'PUT',
      body: { archetype_ids: archetypeIds, min_severity: minSeverity },
    }),

  holdings: () => request<{ holdings: Holding[] }>('/me/holdings'),

  updateHoldings: (holdings: Holding[]) =>
    request<{ holdings: Holding[] }>('/me/holdings', {
      method: 'PUT',
      body: { holdings },
    }),

  portfolioExposure: (eventId: string, holdings: Record<string, number>) =>
    request<PortfolioExposure>('/impact/portfolio', {
      method: 'POST',
      body: { event_id: eventId, holdings },
    }),

  magicLink: (email: string) =>
    request<{ sent: boolean }>('/auth/magic-link', {
      method: 'POST',
      body: { email },
      skipAuthRetry: true,
    }),

  verifyMagicLink: (token: string) =>
    request<AuthSuccess>('/auth/verify', {
      method: 'POST',
      body: { token },
      skipAuthRetry: true,
    }),

  googleSignIn: (idToken: string) =>
    request<AuthSuccess>('/auth/google', {
      method: 'POST',
      body: { id_token: idToken },
      skipAuthRetry: true,
    }),

  logout: () =>
    request<void>('/auth/logout', { method: 'POST', skipAuthRetry: true }),

  pushPublicKey: () => request<{ publicKey: string }>('/push/public-key'),

  pushSubscribe: (subscription: PushSubscriptionJSON) =>
    request<{ id: string }>('/push/subscribe', {
      method: 'POST',
      body: subscription,
    }),

  renderedBeacon: (auditId: string) =>
    request<{ recorded: boolean }>('/explain/rendered', {
      method: 'POST',
      body: { auditId },
    }),
};

// --- domain shapes -------------------------------------------------------
// Hand-written mirrors of the API contract. `pnpm gen:types` regenerates
// types/api.d.ts from the live OpenAPI schema and CI fails on any diff, so a
// backend change breaks the build here rather than at runtime in a user's hand.

export interface ImpactPrior {
  target: string;
  direction: -1 | 0 | 1;
  magnitude_prior_bps: [number, number];
  horizon: string;
  confidence: 'high' | 'medium' | 'low';
  channels: string[];
  rationale: string;
}

export interface ArchetypeDetail {
  id: string;
  label: string;
  family: string;
  description: string;
  detection: Record<string, unknown>;
  impacts: ImpactPrior[];
}

export interface Channel {
  id: string;
  name: string;
  kind: string;
  horizon: 'fast' | 'medium' | 'slow';
  description: string;
  observable_proxies?: string[];
}

export interface AnalogEvent {
  event_id: string;
  event_date: string;
  headline: string;
  similarity: number;
  car_bps: number;
}

export interface AnalogSummary {
  archetype_id: string;
  target: string;
  window: string;
  sample_size: number;
  mean_car_bps: number;
  median_car_bps: number;
  stdev_bps: number;
  hit_rate: number;
  p5_bps: number;
  p95_bps: number;
  t_stat: number;
  p_value: number;
  analogs: AnalogEvent[];
  precomputed?: boolean;
  as_of?: string;
}

export interface CalibrationRow {
  archetype: string;
  target: string;
  status:
    | 'confirmed'
    | 'sign_ok_magnitude_off'
    | 'contradicted'
    | 'underpowered'
    | 'no_data';
  prior_direction: -1 | 0 | 1;
  prior_range_bps?: [number, number];
  realised_median_bps?: number;
  hit_rate?: number;
  sample_size: number;
  p_value?: number;
  confidence?: string;
}

export interface CalibrationReport {
  window: string;
  summary: Record<string, number>;
  rows: CalibrationRow[];
  run_at?: string;
}

export interface DetectedEvent {
  event_id: string;
  archetype_id: string;
  event_date: string;
  headline: string;
  sources: string[];
  match_score: number;
}

export interface DigestSection {
  title: string;
  bullets: string[];
}

export interface Digest {
  digest_date: string;
  generated_at: string;
  headline_summary: string;
  sections: DigestSection[];
  events: DetectedEvent[];
  disclaimer: string;
}

export interface Alert {
  alert_id: string;
  created_at: string;
  severity: 'info' | 'watch' | 'high';
  archetype_id: string;
  headline: string;
  targets: string[];
  body: string;
  disclaimer: string;
}

export interface Holding {
  symbol: string;
  weight: number;
}

export interface MeResponse {
  user: { id: string; email: string; locale: string; tz: string };
  watchlist: { archetypeIds: string[]; minSeverity: string };
  pushEnabled: boolean;
}

export interface AuthSuccess {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: MeResponse['user'];
}

export interface PortfolioExposure {
  disclaimer: string;
  [key: string]: unknown;
}

export interface OfflineBundleAnalog {
  archetypeId: string;
  target: string;
  window: string;
  asOf: string;
  sampleSize: number;
  meanCarBps: number;
  medianCarBps: number;
  stdevBps: number;
  hitRate: number;
  p5Bps: number;
  p95Bps: number;
  tStat: number;
  pValue: number;
  analogs: AnalogEvent[];
}

export interface OfflineBundle {
  generatedAt: string;
  defaultWindow: string;
  archetypes: ArchetypeDetail[];
  channels: Channel[];
  analogSummaries: OfflineBundleAnalog[];
  digest: Digest | null;
  recentEvents: {
    eventId: string;
    archetypeId: string;
    eventDate: string;
    headline: string;
    sources: string[];
    matchScore: number;
  }[];
  disclaimer: string;
  analogDetailOmitted: boolean;
  gzippedBytes?: number;
}
