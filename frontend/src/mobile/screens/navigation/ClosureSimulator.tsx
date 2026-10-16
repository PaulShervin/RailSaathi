// Demo-only: close one pathway of the current route (simulated) and watch the engine reroute.
import { useState } from 'react'
import type { NavDisruption, NavRoute } from '../../../navigation/types'
import { useApp } from '../../PlannerContext'

interface Props {
  route: NavRoute | null
  canSimulate: boolean
  disruptions: NavDisruption[]
  loading: boolean
  nodeName: (id: string) => string
  onClose: (edgeId: string) => void
  onReopenAll: () => void
}

export function ClosureSimulator({ route, canSimulate, disruptions, loading, nodeName, onClose, onReopenAll }: Props) {
  const { m } = useApp()
  const n = m.navigation
  const [closeId, setCloseId] = useState('')
  return (
    <>
      {canSimulate && route && (
        <section className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-ink-100">
          <h2 className="text-sm font-bold text-brand-900">{n.closure}</h2>
          <p className="text-xs text-ink-500">{n.closureHelp}</p>
          <div className="mt-2 flex gap-2">
            <select aria-label={n.closure} value={closeId} onChange={(e) => setCloseId(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-ink-300 px-2 py-1 text-xs">
              <option value="">—</option>
              {route.segments.map((s) => <option key={s.edge_id} value={s.edge_id}>{nodeName(s.from_node)} → {nodeName(s.to_node)}</option>)}
            </select>
            <button type="button" disabled={!closeId || loading} onClick={() => { onClose(closeId); setCloseId('') }}
              className="rounded-lg bg-red-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-40">{n.closeBtn}</button>
          </div>
        </section>
      )}
      {disruptions.length > 0 && (
        <p className="flex items-center justify-between rounded-xl bg-red-50 px-3 py-2 text-xs text-red-800">
          <span>{n.activeClosures}: {disruptions.length}</span>
          <button type="button" onClick={onReopenAll} disabled={loading} className="font-semibold underline">{n.reopenAll}</button>
        </p>
      )}
    </>
  )
}
