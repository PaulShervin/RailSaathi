import { ArrowRight, BellIcon } from '../icons'
import { useApp } from '../PlannerContext'

/**
 * Promotional card for live alerts. It only promises what exists: live-status checks for a
 * confirmed plan (via the current data provider). Push notifications are not connected, and it says so.
 */
export function LiveAlertsPromo() {
  const { planner, go, m } = useApp()
  const confirmed = Boolean(planner.state?.confirmation)
  const health = planner.health
  const live = health?.data_mode === 'live'
  const provider = health?.data_provider?.active
  const d = m.dashboard
  return (
    <section aria-labelledby="alerts-promo-title"
      className="mx-4 mb-4 overflow-hidden rounded-2xl bg-gradient-to-br from-brand-600 to-brand-900 p-4 text-white shadow-card">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/15"><BellIcon size={22} /></span>
        <div className="min-w-0 flex-1">
          <h2 id="alerts-promo-title" className="text-base font-bold">{d.alertsTitle}</h2>
          <p className="mt-0.5 text-sm text-white/85">{d.alertsBody}</p>
          <p className="mt-1.5 text-[11px] text-white/70">{live && provider ? `${d.alertsSource} ${provider}` : d.alertsDemo}</p>
          <p className="text-[11px] text-white/70">{d.alertsNotice}</p>
        </div>
      </div>
      <button type="button" onClick={() => go(confirmed ? 'confirmation' : 'alerts')}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-brand-700 hover:bg-brand-50">
        {confirmed ? d.alertsCheck : d.alertsOpen} <ArrowRight size={16} />
      </button>
    </section>
  )
}
