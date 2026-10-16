// Typed client for station navigation. Served by the main RailSaathi backend (merged from Navigation_exp).
import type { NavDisruption, NavRoute, NavStationResponse, NavStationSummary, RoutePreferences, StationInfo } from './types'

const DEFAULT_BASE = 'http://localhost:8000'
const TIMEOUT_MS = 15_000

export class NavApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'NavApiError'
  }
}

type FetchLike = typeof fetch

function detailText(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string }
    if (d.message) return d.message
  }
  return `Navigation service error (${status})`
}

export function createNavApi(baseUrl?: string, fetchImpl?: FetchLike) {
  const base = (baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE).replace(/\/$/, '')
  const doFetch = fetchImpl ?? fetch.bind(globalThis)

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
    try {
      const res = await doFetch(`${base}${path}`, {
        method,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) throw new NavApiError(res.status, detailText(data, res.status))
      return data as T
    } catch (err) {
      if (err instanceof NavApiError) throw err
      throw new NavApiError(0, 'Cannot reach the RailSaathi server for station navigation. Check that the backend is running.')
    } finally {
      clearTimeout(timer)
    }
  }

  return {
    base,
    imageUrl: (path: string) => `${base}${path}`,
    stations: () => request<NavStationSummary[]>('GET', '/api/stations'),
    station: (id: string) => request<NavStationResponse>('GET', `/api/stations/${encodeURIComponent(id)}`),
    adminStatus: () => request<{ public_disruption_simulation: boolean }>('GET', '/api/admin/status'),
    info: (id: string) => request<StationInfo>('GET', `/api/stations/${encodeURIComponent(id)}/info`),
    route: (stationId: string, source: string, destination: string, preferences: RoutePreferences, previousEdgeIds: string[] = []) =>
      request<NavRoute>('POST', '/api/navigation/route', {
        station_id: stationId, source, destination, preferences, previous_edge_ids: previousEdgeIds,
      }),
    disruptions: (stationId: string) => request<NavDisruption[]>('GET', `/api/stations/${encodeURIComponent(stationId)}/disruptions`),
    closeEdge: (stationId: string, edgeId: string) =>
      request<NavDisruption>('POST', `/api/stations/${encodeURIComponent(stationId)}/disruptions`, {
        target_type: 'edge', target_id: edgeId, reason: 'Simulated closure (passenger app demo)',
      }),
    removeDisruption: (stationId: string, eventId: string) =>
      request<{ deleted: string }>('DELETE', `/api/stations/${encodeURIComponent(stationId)}/disruptions/${encodeURIComponent(eventId)}`),
  }
}

export type NavApi = ReturnType<typeof createNavApi>
export const navApi = createNavApi()

/** Planner station code → navigation station id. Only stations with a traced floor plan appear here. */
export const NAV_STATION_FOR_CODE: Record<string, string> = { MAS: 'chennai_central' }
