// Origin / destination selectors with a swap button. Options are the station's named places
// (junction nodes are hidden by the hook).
import type { NavNode } from '../../../navigation/types'
import { useApp } from '../../PlannerContext'

interface Props {
  places: NavNode[]
  from: string
  to: string
  sameEndpoints: boolean
  onFrom: (id: string) => void
  onTo: (id: string) => void
  onSwap: () => void
}

export function EndpointPicker({ places, from, to, sameEndpoints, onFrom, onTo, onSwap }: Props) {
  const { m } = useApp()
  const n = m.navigation
  const selectClass = 'mt-0.5 w-full min-w-0 rounded-xl border border-ink-300 bg-white px-2.5 py-2 text-sm font-medium text-ink-900'
  return (
    <div className="rounded-2xl bg-white p-3 shadow-card ring-1 ring-ink-100">
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2">
        <span aria-hidden="true" className="h-3 w-3 rounded-full bg-match-600 ring-2 ring-match-50" />
        <label className="block text-xs font-medium text-ink-500">{n.from}
          <select aria-label={n.from} value={from} onChange={(e) => onFrom(e.target.value)} className={selectClass}>
            {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <button type="button" aria-label={n.swap} title={n.swap} disabled={!to} onClick={onSwap}
          className="row-span-2 grid h-10 w-10 place-items-center rounded-full bg-brand-50 text-lg font-bold text-brand-700 ring-1 ring-brand-100 disabled:opacity-40">
          ⇅
        </button>
        <span aria-hidden="true" className="h-3 w-3 rounded-full bg-red-600 ring-2 ring-red-100" />
        <label className="block text-xs font-medium text-ink-500">{n.to}
          <select aria-label={n.to} value={to} onChange={(e) => onTo(e.target.value)} className={selectClass}>
            <option value="">{n.choose}</option>
            {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      </div>
      {sameEndpoints && <p role="alert" className="mt-2 rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-900">{n.sameEndpoints}</p>}
    </div>
  )
}
