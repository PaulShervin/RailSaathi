// Station-navigation state for the mobile screen. All routing happens on the backend
// (app/navigation: Dijkstra over traced walkways); this hook only calls the API and holds results.
//
// The route is recalculated automatically whenever the start, destination or preferences change,
// so the map and the step list always show the route the engine last returned for those inputs.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavApiError, navApi as defaultApi, type NavApi } from './navApi'
import type { NavDisruption, NavRoute, NavStationResponse, NavStationSummary, RoutePreferences } from './types'

const SELECTABLE_TYPES = new Set(['entrance', 'platform', 'platform_access', 'ticket_counter', 'toilet',
  'information_desk', 'shop', 'other_facility', 'concourse'])

export const NO_PREFS: RoutePreferences = { avoid_stairs: false, wheelchair: false, require_verified_accessibility: false }

export function useStationNav(preferredStationId: string | null, initialPrefs: RoutePreferences, api: NavApi = defaultApi) {
  const [stations, setStations] = useState<NavStationSummary[]>([])
  const [stationId, setStationId] = useState<string | null>(null)
  const [data, setData] = useState<NavStationResponse | null>(null)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [prefs, setPrefs] = useState<RoutePreferences>(initialPrefs)
  const [route, setRoute] = useState<NavRoute | null>(null)
  const [previousGeometry, setPreviousGeometry] = useState<NavRoute['geometry']>([])
  const [disruptions, setDisruptions] = useState<NavDisruption[]>([])
  const [canSimulate, setCanSimulate] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Index of the instruction the passenger has stepped to (manual turn-by-turn), or null when not navigating.
  const [navStep, setNavStep] = useState<number | null>(null)
  const requestSeq = useRef(0) // ignores responses that arrive after a newer request

  const fail = (err: unknown) => setError(err instanceof NavApiError ? err.message : String(err))

  // Load the station list once, then pick the journey's station if it has a floor plan.
  useEffect(() => {
    api.stations().then((list) => {
      setStations(list)
      const pick = list.find((s) => s.station_id === preferredStationId) ?? list[0]
      setStationId(pick?.station_id ?? null)
    }).catch(fail)
    api.adminStatus().then((s) => setCanSimulate(s.public_disruption_simulation)).catch(() => setCanSimulate(false))
  }, [api, preferredStationId])

  // Load the station graph and its active (simulated) closures whenever the station changes.
  useEffect(() => {
    if (!stationId) return
    setData(null); setRoute(null); setPreviousGeometry([]); setError(null); setNavStep(null)
    Promise.all([api.station(stationId), api.disruptions(stationId)]).then(([station, active]) => {
      setData(station)
      setDisruptions(active)
      const first = station.station.nodes.find((n) => n.type === 'entrance')
      setFrom(first?.id ?? '')
      setTo('')
    }).catch(fail)
  }, [api, stationId])

  const places = useMemo(
    () => (data?.station.nodes ?? []).filter((n) => SELECTABLE_TYPES.has(n.type)),
    [data],
  )
  const nodeName = useCallback((id: string) => data?.station.nodes.find((n) => n.id === id)?.name ?? id, [data])
  const sameEndpoints = Boolean(from && to && from === to)

  const findRoute = useCallback(async (previousEdgeIds: string[] = []) => {
    if (!stationId || !from || !to || from === to) return null
    const seq = ++requestSeq.current
    setLoading(true); setError(null)
    try {
      const result = await api.route(stationId, from, to, prefs, previousEdgeIds)
      if (seq !== requestSeq.current) return null
      setRoute(result)
      setNavStep(null)
      return result
    } catch (err) {
      if (seq === requestSeq.current) fail(err)
      return null
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
  }, [api, stationId, from, to, prefs])

  // Recalculate whenever the endpoints or preferences change (and clear a stale route when they become invalid).
  useEffect(() => {
    if (!data) return
    if (!from || !to || from === to) { setRoute(null); setNavStep(null); return }
    void findRoute()
  }, [data, from, to, prefs, findRoute])

  const swap = useCallback(() => {
    if (!to) return
    const f = from
    setFrom(to)
    setTo(f)
  }, [from, to])

  /** Close one pathway (simulated), then reroute and explain whether the old route is blocked. */
  const closePathway = useCallback(async (edgeId: string) => {
    if (!stationId || !route) return
    setLoading(true); setError(null)
    try {
      const event = await api.closeEdge(stationId, edgeId)
      setDisruptions((prev) => [...prev, event])
      setPreviousGeometry(route.geometry)
    } catch (err) {
      fail(err)
      setLoading(false)
      return
    }
    setLoading(false)
    await findRoute(route.edge_ids)
  }, [api, stationId, route, findRoute])

  const reopenAll = useCallback(async () => {
    if (!stationId) return
    setLoading(true); setError(null)
    try {
      await Promise.all(disruptions.map((d) => api.removeDisruption(stationId, d.id)))
      setDisruptions([])
      setPreviousGeometry([])
    } catch (err) {
      fail(err)
    } finally {
      setLoading(false)
    }
    if (route) await findRoute()
  }, [api, stationId, disruptions, route, findRoute])

  // Manual turn-by-turn: the passenger advances the instructions in order. There is no indoor
  // positioning source, so the "current position" is the node of the selected step, not a real fix.
  const stepCount = route?.status === 'ok' ? route.instructions.length : 0
  const startNavigation = useCallback(() => { if (stepCount > 0) setNavStep(0) }, [stepCount])
  const nextStep = useCallback(() => setNavStep((s) => (s === null ? null : Math.min(stepCount - 1, s + 1))), [stepCount])
  const prevStep = useCallback(() => setNavStep((s) => (s === null ? null : Math.max(0, s - 1))), [])
  const exitNavigation = useCallback(() => setNavStep(null), [])
  const currentNodeId = navStep !== null && route?.status === 'ok' ? route.instructions[navStep]?.node_id ?? null : null

  return {
    api, stations, stationId, setStationId, data, places, nodeName,
    from, setFrom, to, setTo, swap, sameEndpoints, prefs, setPrefs,
    route, previousGeometry, disruptions, canSimulate, loading, error,
    findRoute, closePathway, reopenAll,
    navStep, stepCount, currentNodeId, startNavigation, nextStep, prevStep, exitNavigation,
  }
}

export type StationNav = ReturnType<typeof useStationNav>
