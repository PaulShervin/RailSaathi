// Station navigation, connected to the backend's indoor routing (app/navigation: Dijkstra over the
// traced walkway graph). Routes, instructions, distances and closures all come from the API; the
// map and the step list render the same route object, so the two views never disagree.
import { useEffect, useMemo, useState } from 'react'
import { NAV_STATION_FOR_CODE } from '../../navigation/navApi'
import { RouteMap } from '../../navigation/RouteMap'
import type { RoutePreferences } from '../../navigation/types'
import { NO_PREFS, useStationNav } from '../../navigation/useStationNav'
import { formatDay, formatTime } from '../../utils/format'
import { AlertIcon, ArrowRight, HomeIcon, InfoIcon, MapIcon, PinIcon, StepsIcon, TrainIcon } from '../icons'
import { useApp } from '../PlannerContext'
import { AppHeader, PrimaryButton, Screen, SecondaryButton, selectedRecommendation } from '../ui'
import { ClosureSimulator } from './navigation/ClosureSimulator'
import { EndpointPicker } from './navigation/EndpointPicker'
import { NavBanner } from './navigation/NavBanner'
import { PreferenceChips, preferenceLabels } from './navigation/PreferenceChips'
import { RouteSummary } from './navigation/RouteSummary'
import { StepList } from './navigation/StepList'

export default function StationNavigation() {
  const { planner, go, m } = useApp()
  const n = m.navigation
  const rec = selectedRecommendation(planner.state)
  const leg = rec?.option.legs[0]
  const needs = planner.state?.journey.passenger_needs ?? []
  const preferredStation = leg ? NAV_STATION_FOR_CODE[leg.from_code] ?? NAV_STATION_FOR_CODE[rec!.option.legs.slice(-1)[0].to_code] ?? null : null
  // Keyed on the needs' contents: `needs` is a new [] each render while no session is loaded,
  // and depending on the array itself caused an infinite render loop.
  const needsKey = [...needs].sort().join(',')
  const needPrefs = useMemo<RoutePreferences>(() => {
    const has = (need: string) => needsKey.split(',').includes(need)
    return { ...NO_PREFS, wheelchair: has('wheelchair'), avoid_stairs: has('wheelchair') || has('reduced_walking') }
  }, [needsKey])
  const nav = useStationNav(preferredStation, needPrefs)
  // Apply the planner's passenger needs when they arrive (the session may load after this screen),
  // but never override toggles the passenger has changed here.
  const [prefsTouched, setPrefsTouched] = useState(false)
  const { setPrefs } = nav
  useEffect(() => {
    if (!prefsTouched) setPrefs(needPrefs)
  }, [needPrefs, prefsTouched, setPrefs])
  const [view, setView] = useState<'map' | 'steps'>('map')
  const route = nav.route
  const ok = route?.status === 'ok' ? route : null
  const station = nav.data?.station
  const navigating = nav.navStep !== null && ok !== null
  const currentInstruction = navigating ? ok.instructions[nav.navStep!] : null
  const lastStep = navigating && nav.navStep === nav.stepCount - 1

  const togglePref = (key: keyof RoutePreferences) => {
    setPrefsTouched(true)
    nav.setPrefs({ ...nav.prefs, [key]: !nav.prefs[key] })
  }
  const activePrefs = preferenceLabels(n).filter(([key]) => nav.prefs[key])

  const footer = station ? (
    navigating ? (
      <div className="flex gap-2">
        <div className="w-1/3"><SecondaryButton onClick={nav.exitNavigation}>{n.exitNav}</SecondaryButton></div>
        <div className="flex-1">
          <PrimaryButton onClick={lastStep ? nav.exitNavigation : nav.nextStep}>
            {lastStep ? n.finish : n.nextStep} <ArrowRight size={20} />
          </PrimaryButton>
        </div>
      </div>
    ) : ok ? (
      <PrimaryButton onClick={() => { nav.startNavigation(); setView('map') }}>{n.startNav} <ArrowRight size={20} /></PrimaryButton>
    ) : (
      <PrimaryButton disabled>{nav.loading ? n.calculating : n.choose}</PrimaryButton>
    )
  ) : undefined

  return (
    <Screen footer={footer}>
      <AppHeader right={(
        <button type="button" onClick={() => go('home')} aria-label={n.home} title={n.home} className="rounded-full p-1.5 text-brand-900 hover:bg-ink-100">
          <HomeIcon size={22} />
        </button>
      )} />

      <NavBanner stationName={station?.station_name ?? null} dataStatus={nav.data?.metadata?.data_status} />

      <section className="mx-4 mt-3 flex items-start gap-3 rounded-2xl bg-white p-3 shadow-card ring-1 ring-ink-100">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><TrainIcon size={22} /></span>
        {leg ? (
          <div className="text-sm">
            <p className="font-bold text-brand-900">{leg.train_no} {leg.train_name}</p>
            <p className="text-ink-500">{n.platformUnknown}</p>
            <p className="text-ink-500">{n.departs} {formatTime(leg.departure)} ({formatDay(leg.departure)}) · {leg.from_name}</p>
          </div>
        ) : <p className="text-sm text-ink-500">{n.noTrain}</p>}
      </section>

      {nav.error && (
        <p role="alert" className="mx-4 mt-3 flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-800">
          <AlertIcon size={18} className="mt-0.5 shrink-0" /> {nav.error}
        </p>
      )}

      {station && (
        <div className="space-y-3 px-4 pb-4 pt-3">
          {nav.stations.length > 1 && (
            <div className="flex items-center gap-2 text-sm">
              <PinIcon size={18} className="text-brand-600" />
              <select aria-label={n.station} value={nav.stationId ?? ''} onChange={(e) => nav.setStationId(e.target.value)}
                className="flex-1 rounded-lg border border-ink-300 px-2 py-1 font-semibold">
                {nav.stations.map((s) => <option key={s.station_id} value={s.station_id}>{s.station_name}</option>)}
              </select>
            </div>
          )}

          <EndpointPicker places={nav.places} from={nav.from} to={nav.to} sameEndpoints={nav.sameEndpoints}
            onFrom={nav.setFrom} onTo={nav.setTo} onSwap={nav.swap} />

          <PreferenceChips prefs={nav.prefs} onToggle={togglePref} />

          <div role="tablist" aria-label={n.title} className="grid grid-cols-2 gap-2">
            {([['map', n.mapView, MapIcon], ['steps', n.steps, StepsIcon]] as const).map(([key, text, Icon]) => (
              <button key={key} type="button" role="tab" aria-selected={view === key} onClick={() => setView(key)}
                className={`flex items-center justify-center gap-2 rounded-full py-2.5 text-sm font-bold ring-2 ${view === key ? 'bg-brand-600 text-white ring-brand-600' : 'bg-white text-brand-700 ring-brand-600'}`}>
                <Icon size={18} /> {text}
              </button>
            ))}
          </div>

          {view === 'map' ? (
            <RouteMap station={station} imageUrl={nav.api.imageUrl(station.map.image)} route={route}
              previousGeometry={nav.previousGeometry} closedEdgeIds={nav.disruptions.filter((d) => d.target_type === 'edge').map((d) => d.target_id)}
              currentNodeId={nav.currentNodeId} loading={nav.loading} nodeName={nav.nodeName}
              labels={{ zoomIn: n.zoomIn, zoomOut: n.zoomOut, locate: n.locate, north: n.north, start: n.startLabel,
                destination: n.destinationLabel, currentStep: n.demoPosition, loading: n.calculating, empty: nav.sameEndpoints ? n.sameEndpoints : n.emptyMap }} />
          ) : (
            <StepList instructions={ok?.instructions ?? []} activeStep={nav.navStep} emptyText={nav.loading ? n.calculating : n.emptySteps} />
          )}

          {currentInstruction && (
            <section role="status" aria-live="polite" className="rounded-2xl bg-brand-50 p-3 ring-2 ring-brand-500">
              <p className="text-[11px] font-bold uppercase tracking-wide text-brand-700">
                {n.stepOf.replace('{n}', String(nav.navStep! + 1)).replace('{total}', String(nav.stepCount))}
              </p>
              <p className="mt-1 text-sm font-semibold text-ink-900">{currentInstruction.text}</p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <button type="button" onClick={nav.prevStep} disabled={nav.navStep === 0} className="text-xs font-semibold text-brand-700 underline disabled:opacity-40">{n.prevStep}</button>
                <p className="flex items-start gap-1 text-[11px] text-ink-500"><InfoIcon size={14} className="mt-0.5 shrink-0" /> {n.positionNote}</p>
              </div>
            </section>
          )}

          {ok && <RouteSummary route={ok} prefs={nav.prefs} nodeName={nav.nodeName} />}

          {route?.status === 'no_route' && (
            <section role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
              <h2 className="font-bold">{n.noRoute}</h2>
              <p className="mt-1">{route.explanation}</p>
              {route.reason === 'accessibility_constraints' && activePrefs.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs font-semibold">{n.relaxHint}</p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {activePrefs.map(([key, text]) => (
                      <button key={key} type="button" onClick={() => togglePref(key)}
                        className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-red-900 ring-1 ring-red-300">✕ {text}</button>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {ok && ok.along_the_way.length > 0 && (
            <section className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-ink-100">
              <h2 className="text-sm font-bold text-brand-900">{n.alongWay}</h2>
              <ul className="mt-2 space-y-1.5">
                {ok.along_the_way.map((a) => (
                  <li key={a.node_id} className="flex items-center gap-2 text-sm">
                    <span className="flex-1 text-ink-900">{a.name}
                      {a.distance_from_route_m !== null && !a.on_route && <span className="text-xs text-ink-500"> · ~{Math.round(a.distance_from_route_m)} m off route</span>}
                    </span>
                    <button type="button" onClick={() => nav.setTo(a.node_id)} className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-semibold text-brand-700">{n.goHere}</button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
            <InfoIcon size={16} className="mt-0.5 shrink-0" /> {n.unverified}
          </p>

          <ClosureSimulator route={ok} canSimulate={nav.canSimulate} disruptions={nav.disruptions} loading={nav.loading}
            nodeName={nav.nodeName} onClose={(id) => void nav.closePathway(id)} onReopenAll={() => void nav.reopenAll()} />
        </div>
      )}
    </Screen>
  )
}
