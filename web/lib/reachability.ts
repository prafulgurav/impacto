/**
 * Is the network actually reachable?
 *
 * `navigator.onLine` answers a different, weaker question: whether the device
 * has *a* network interface up. It is true on a captive portal, true on a dead
 * cell connection, and — as CI demonstrated — true in a browser that is being
 * held offline at the network layer while the page is provably being served
 * from the service worker's cache.
 *
 * For most apps that is a cosmetic bug. Here it is a correctness one: the
 * offline banner is what attaches an age to the figures on screen, and a stale
 * abnormal return presented as today's is exactly the misleading output this
 * product's rules exist to prevent. So the banner asks the network, and only
 * falls back to the flag.
 *
 * The probe hits /api/health, which the service worker routes NetworkOnly. A
 * thrown fetch means no network; any response at all — including a 5xx — means
 * the network is there, which is the only thing being asked.
 */

const PROBE_URL = '/api/health';
const PROBE_TIMEOUT_MS = 4_000;

export async function isReachable(): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    // The flag lies about being online, but it is trustworthy when it says
    // offline — and believing it saves a request that cannot succeed.
    return false;
  }
  if (typeof fetch === 'undefined') return true;

  try {
    const response = await fetch(PROBE_URL, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'omit',
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    // Deliberately not response.ok: a 503 from the API is a backend problem,
    // not a connectivity one, and it should not claim the device is offline.
    return response.type !== 'error';
  } catch {
    return false;
  }
}
