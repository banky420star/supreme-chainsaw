import React from 'react'
import { fetchScenarios, RegimesResponse, RegimeStats } from '../services/api'

interface Props {
  scenarios?: RegimesResponse
}

function fmt(v: number | undefined | null, dec = 1): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(dec)
}

function pct(v: number | undefined | null): string {
  if (v == null || isNaN(v)) return '--'
  return `${(v * 100).toFixed(1)}%`
}

function regimeColor(regime: string): string {
  const r = regime.toLowerCase()
  if (r.includes('bull') || r.includes('up') || r.includes('trend')) return 'var(--green)'
  if (r.includes('bear') || r.includes('down') || r.includes('crash')) return 'var(--red)'
  if (r.includes('chop') || r.includes('range') || r.includes('flat')) return 'var(--amber)'
  return 'var(--cyan)'
}

const ScenarioMemoryPanel: React.FC<Props> = ({ scenarios: propScenarios }) => {
  const [data, setData] = React.useState<RegimesResponse | null>(propScenarios ?? null)
  const [loading, setLoading] = React.useState(!propScenarios)

  /* fetch from /api/regimes if parent didn't supply pre-fetched data */
  React.useEffect(() => {
    if (propScenarios) { setData(propScenarios); setLoading(false); return }
    const load = async () => {
      try {
        const res = await fetchScenarios()
        setData(res)
      } catch { /* ignore */ }
      setLoading(false)
    }
    load()
    const iv = setInterval(load, 15_000)
    return () => clearInterval(iv)
  }, [propScenarios])

  /* also accept legacy /api/scenarios format */
  const [legacy, setLegacy] = React.useState<any[]>([])
  React.useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch('/api/scenarios')
        if (res.ok) {
          const d = await res.json()
          const rows = d.recent_scenarios || d.scenarios || []
          setLegacy(rows)
        }
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const regimes = data?.regimes ?? {}
  const regimeEntries = Object.entries(regimes) as [string, RegimeStats][]
  const hasRegimes = regimeEntries.length > 0
  const hasLegacy  = legacy.length > 0

  return (
    <div className="animate-in">
      <div
        className="agit-panel"
        style={{ marginBottom: 'var(--gap)' }}
      >
        <div className="agit-panel-title">Scenario Memory</div>
        <p style={{ fontSize: '0.78rem', color: 'var(--muted)', margin: 0, lineHeight: 1.6 }}>
          Regime-labelled market scenarios discovered by the learning pipeline.
          Each entry shows how the trading stack behaves in that market state.
        </p>
      </div>

      {loading && (
        <div className="agit-panel agit-empty">
          <div className="agit-skeleton" style={{ width: 200, height: 14, marginBottom: 8 }} />
          <div className="agit-skeleton" style={{ width: 320, height: 10 }} />
        </div>
      )}

      {/* Regime Statistics from /api/regimes */}
      {!loading && hasRegimes && (
        <div style={{ marginBottom: 'var(--gap)' }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--dim)', marginBottom: 12 }}>
            Regime Statistics
          </div>
          <div className="agit-signal-cards">
            {regimeEntries.map(([regime, stats]) => {
              const totalDir = (stats.buy_count ?? 0) + (stats.sell_count ?? 0) + (stats.hold_count ?? 0) || 1
              const buyPct   = ((stats.buy_count  ?? 0) / totalDir) * 100
              const sellPct  = ((stats.sell_count ?? 0) / totalDir) * 100
              const holdPct  = ((stats.hold_count ?? 0) / totalDir) * 100
              const color = regimeColor(regime)

              return (
                <div key={regime} className="agit-signal-card" style={{ borderTopColor: color, borderTopWidth: 2, borderTopStyle: 'solid' }}>
                  <div className="agit-signal-card-header">
                    <span className="agit-signal-symbol" style={{ color }}>
                      {regime.toUpperCase()}
                    </span>
                    <span className="agit-badge agit-badge-info" style={{ fontSize: '0.6rem' }}>
                      {stats.total_decisions ?? 0} decisions
                    </span>
                  </div>

                  {/* KPI row */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
                    <div>
                      <div style={{ fontSize: '0.6rem', color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2 }}>Avg Confidence</div>
                      <div style={{ fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--text)', fontSize: '1.1rem' }}>
                        {pct(stats.avg_confidence)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.6rem', color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2 }}>Avg Exposure</div>
                      <div style={{ fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--amber)', fontSize: '1.1rem' }}>
                        {fmt(stats.avg_exposure, 2)}
                      </div>
                    </div>
                  </div>

                  {/* Direction breakdown bar */}
                  <div style={{ marginBottom: 6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.62rem', fontFamily: 'var(--mono)', color: 'var(--dim)', marginBottom: 4 }}>
                      <span>BUY {fmt(buyPct, 0)}%</span>
                      <span>HOLD {fmt(holdPct, 0)}%</span>
                      <span>SELL {fmt(sellPct, 0)}%</span>
                    </div>
                    <div className="agit-blend-bar">
                      <div style={{ width: `${buyPct}%`,  background: 'var(--green)',  transition: 'width 0.4s ease' }} />
                      <div style={{ width: `${holdPct}%`, background: 'var(--amber)',  transition: 'width 0.4s ease' }} />
                      <div style={{ width: `${sellPct}%`, background: 'var(--red)',    transition: 'width 0.4s ease' }} />
                    </div>
                  </div>

                  {/* Active symbols */}
                  {stats.symbols && stats.symbols.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                      {stats.symbols.slice(0, 6).map((sym) => (
                        <span key={sym} className="agit-badge agit-badge-idle" style={{ fontSize: '0.58rem' }}>{sym}</span>
                      ))}
                      {stats.symbols.length > 6 && (
                        <span className="agit-badge agit-badge-idle" style={{ fontSize: '0.58rem' }}>+{stats.symbols.length - 6}</span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Legacy /api/scenarios rows */}
      {hasLegacy && (
        <div style={{ marginBottom: 'var(--gap)' }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--dim)', marginBottom: 12 }}>
            Recent Scenarios
          </div>
          <div className="agit-scenario-list">
            {legacy.map((s: any, i: number) => (
              <div key={i} className="agit-scenario-row">
                <div className="agit-scenario-rank">#{i + 1}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, color: 'var(--cyan)', marginBottom: 4, fontSize: '0.85rem' }}>
                    {s.scenario || s.label || `Scenario ${i + 1}`}
                  </div>
                  <div style={{ display: 'flex', gap: 16, fontSize: '0.72rem', fontFamily: 'var(--mono)', color: 'var(--muted)', flexWrap: 'wrap' }}>
                    {s.win_rate   != null && <span><span style={{ color: 'var(--green)' }}>WR</span> {(s.win_rate * 100).toFixed(1)}%</span>}
                    {s.avg_pnl    != null && <span><span style={{ color: 'var(--amber)' }}>PNL</span> ${s.avg_pnl.toFixed(2)}</span>}
                    {s.trade_count != null && <span><span style={{ color: 'var(--dim)' }}>TRADES</span> {s.trade_count}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && !hasRegimes && !hasLegacy && (
        <div className="agit-panel agit-empty">
          <div className="agit-empty-text">
            No scenario data yet — the learning pipeline will populate this as trades are analyzed and regimes are classified.
          </div>
        </div>
      )}
    </div>
  )
}

export default ScenarioMemoryPanel
